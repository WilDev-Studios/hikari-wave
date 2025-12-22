from __future__ import annotations

from collections import deque
from hikariwave.config import BufferMode
from hikariwave.internal.constants import Audio
from typing import TYPE_CHECKING

import aiofiles
import asyncio
import os

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

__all__ = ("FrameStore",)

class FrameStore:
    """Mode-switching capable storage buffer."""

    __slots__ = (
        "_connection", "_live_buffer", "_frames_per_second", "_memory_limit",
        "_read_lock", "_chunk_lock", "_chunk_buffer", "_chunk_frame_limit", "_chunk_frame_count",
        "_disk_queue", "_current_file", "_current_file_path", "_file_index",
        "_low_mark", "_high_mark", "_refilling", "_eos_written", "_eos_emitted", "_event", "_read_task",
    )

    def __init__(self, connection: VoiceConnection) -> None:
        """
        Create a new frame storage object.
        
        Parameters
        ----------
        connection : VoiceConnection
            The current active connection.
        """

        self._connection: VoiceConnection = connection

        self._live_buffer: asyncio.Queue[bytes | None] = asyncio.Queue()

        self._frames_per_second: int = 1000 // Audio.FRAME_LENGTH
        self._memory_limit: int = (
            self._connection._config.buffer.duration * self._frames_per_second
            if self._connection._config.buffer.mode == BufferMode.DISK and self._connection._config.buffer.duration else 0
        )

        self._read_lock: asyncio.Lock = asyncio.Lock()
        self._chunk_lock: asyncio.Lock = asyncio.Lock()
        self._chunk_buffer: bytearray = bytearray()
        self._chunk_frame_limit: int = self._memory_limit
        self._chunk_frame_count: int = 0

        self._disk_queue: deque[int] = deque()
        self._current_file: aiofiles.threadpool.binary.AsyncBufferedReader | None = None
        self._current_file_path: str | None = None
        self._file_index: int = 0

        self._low_mark: int = self._memory_limit // 4
        self._high_mark: int = self._memory_limit
        self._refilling: bool = False

        self._eos_written: bool = False
        self._eos_emitted: bool = False

        self._event: asyncio.Event = asyncio.Event()
        self._read_task: asyncio.Task[None] | None = None

        if self._connection._config.buffer.mode == BufferMode.DISK:
            os.makedirs(f"wavecache/{self._connection._guild_id}", exist_ok=True)
    
    async def _flush_chunk(self) -> None:
        if not self._chunk_buffer:
            return

        self._file_index += 1

        async with aiofiles.open(f"wavecache/{self._connection._guild_id}/{self._file_index}.wcf", "wb") as file:
            await file.write(self._chunk_buffer)
        
        self._disk_queue.append(self._file_index)
        self._chunk_buffer.clear()
        self._chunk_frame_count = 0

    async def _read_chunk(self) -> None:
        try:
            async with self._read_lock:
                if self._refilling or not self._disk_queue:
                    return
            
                self._refilling = True
                file_index: int = self._disk_queue.popleft()

                try:
                    path: str = f"wavecache/{self._connection._guild_id}/{file_index}.wcf"

                    async with aiofiles.open(path, "rb") as file:
                        batch: list[bytes] = []
                        
                        while True:
                            length_bytes: bytes = await file.read(2)
                            if not length_bytes:
                                break

                            batch.append(await file.read(int.from_bytes(length_bytes, "big")))
                    
                            if len(batch) >= 100:
                                for frame in batch: await self._live_buffer.put(frame)

                                batch.clear()
                                await asyncio.sleep(0)
                        
                        for frame in batch: await self._live_buffer.put(frame)

                    os.remove(path)

                    if not self._disk_queue and self._eos_written:
                        await self._live_buffer.put(None)
                finally:
                    self._refilling = False
                    self._event.set()
        except asyncio.CancelledError:
            return

    async def clear(self) -> None:
        """
        Clear all internal buffers and stop any operations.
        """
        
        async with self._read_lock:
            if self._read_task:
                self._read_task.cancel()

                try:
                    await self._read_task
                except asyncio.CancelledError:
                    pass

                self._read_task = None
        
        self._event.clear()
        self._eos_written = False
        self._eos_emitted = False
        self._refilling = False
        self._file_index = 0
        self._current_file_path = None
        self._current_file = None

        self._chunk_frame_count = 0
        self._chunk_buffer.clear()

        while not self._live_buffer.empty():
            try:
                self._live_buffer.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._connection._config.buffer.mode == BufferMode.DISK:
            while self._disk_queue:
                index = self._disk_queue.popleft()
                path = f"wavecache/{self._connection._guild_id}/{index}.wcf"

                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            
            try:
                for filename in os.listdir(f"wavecache/{self._connection._guild_id}"):
                    if filename.endswith(".wcf"):
                        os.remove(os.path.join("wavecache", f"{self._connection._guild_id}", filename))
            except OSError:
                pass

    async def fetch_frame(self) -> bytes | None:
        """
        Fetch the next available frame.
        """
        
        while True:
            if not self._live_buffer.empty():
                frame: bytes | bytes =  await self._live_buffer.get()
            
                if self._connection._config.buffer.mode == BufferMode.DISK and self._live_buffer.qsize() <= self._low_mark and self._disk_queue:
                    if self._read_task is None or self._read_task.done():
                        self._read_task = asyncio.create_task(self._read_chunk())
                
                return frame
            
            if self._eos_written and not self._disk_queue and not self._refilling:
                if not self._eos_emitted:
                    self._eos_emitted = True
                
                return None
            
            self._event.clear()
            await self._event.wait()

    async def store_frame(self, frame: bytes | None) -> None:
        """
        Store a frame.
        
        Parameters
        ----------
        frame : bytes | None
            The frame to store.
        """
        
        if self._connection._config.buffer.mode == BufferMode.MEMORY:
            await self._live_buffer.put(frame)
            self._event.set()
            return
        
        if frame is None:
            self._eos_written = True

            async with self._chunk_lock:
                await self._flush_chunk()

            if not self._disk_queue:
                await self._live_buffer.put(None)
    
            self._event.set()
            return
        
        has_backlog: bool = bool(self._disk_queue) or bool(self._chunk_buffer)
        
        if not has_backlog and self._live_buffer.qsize() < self._high_mark:
            await self._live_buffer.put(frame)
            self._event.set()
            return
        
        async with self._chunk_lock:
            self._chunk_buffer.extend(len(frame).to_bytes(2, "big") + frame)
            self._chunk_frame_count += 1

            if self._chunk_frame_count >= self._chunk_frame_limit:
                await self._flush_chunk()
                self._event.set()
    
    async def wait(self) -> None:
        """
        Wait until the store is available to read from.
        """
        
        if not self._live_buffer.empty() or (self._eos_written and not self._disk_queue):
            return
        
        self._event.clear()
        await self._event.wait()
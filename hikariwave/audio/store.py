from __future__ import annotations

from collections import deque
from hikariwave.config import BufferMode
from hikariwave.internal.constants import Audio
from hikariwave.internal.dev import log_exception
from typing import TYPE_CHECKING

import aiofiles
import asyncio
import os

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

__all__ = ()

class FrameStore:
    """Mode-switching capable storage buffer."""

    __slots__ = (
        "_connection", "_live_buffer", "_generation", "_frames_per_second", "_memory_limit",
        "_read_lock", "_chunk_buffer", "_chunk_frame_limit", "_chunk_frame_count",
        "_disk_queue", "_file_index", "_low_mark", "_high_mark", "_refilling",
        "_eos_written", "_eos_emitted", "_event", "_read_task", "_write_task",
        "_write_queue", "_active_chunk", "_write_event", "_shutdown",
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
        self._generation: int = 0

        self._frames_per_second: int = 1000 // Audio.FRAME_LENGTH
        self._memory_limit: int = (
            self._connection._config.buffer.duration * self._frames_per_second
            if self._connection._config.buffer.mode == BufferMode.DISK and self._connection._config.buffer.duration else 0
        )

        self._read_lock: asyncio.Lock = asyncio.Lock()

        self._chunk_buffer: bytearray = bytearray()
        self._active_chunk: bytearray = bytearray()
        self._chunk_frame_limit: int = self._memory_limit
        self._chunk_frame_count: int = 0

        self._disk_queue: deque[int] = deque()
        self._file_index: int = 0

        self._low_mark: int = self._memory_limit // 4
        self._high_mark: int = self._memory_limit
        self._refilling: bool = False

        self._eos_written: bool = False
        self._eos_emitted: bool = False

        self._event: asyncio.Event = asyncio.Event()
        self._write_event: asyncio.Event = asyncio.Event()
        self._read_task: asyncio.Task[None] | None = None
        self._write_task: asyncio.Task[None] | None = None
        self._write_queue: asyncio.Queue[tuple[int, bytearray] | None] = asyncio.Queue()
        self._shutdown: bool = False

        if self._connection._config.buffer.mode == BufferMode.DISK:
            os.makedirs(f"wavecache/{self._connection._guild_id}", exist_ok=True)
            self._write_task = connection._client._tasks.create(self._disk_writer(), name="store-writer")

    async def _disk_writer(self) -> None:
        try:
            while not self._shutdown:
                item: tuple[int, bytearray] = await self._write_queue.get()

                if item is None:
                    break

                file_index, data = item
                path: str = f"wavecache/{self._connection._guild_id}/{file_index}.wcf"

                try:
                    async with aiofiles.open(path, "wb") as file:
                        await file.write(data)

                    self._disk_queue.append(file_index)
                    self._event.set()
                except Exception as e:
                    log_exception(e)
                    pass

                del data
        except asyncio.CancelledError as e:
            log_exception(e)
            pass

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
                        content: bytes = await file.read()

                    try:
                        os.remove(path)
                    except OSError as e:
                        log_exception(e)
                        pass

                    offset: int = 0
                    batch: list[bytes] = []

                    while offset < len(content):
                        if offset + 2 > len(content):
                            break

                        length: int = int.from_bytes(content[offset:offset + 2], "big")
                        offset += 2

                        if offset + length > len(content):
                            break

                        batch.append(content[offset:offset + length])
                        offset += length

                        if len(batch) >= 100:
                            for frame in batch:
                                self._live_buffer.put_nowait(frame)

                            batch.clear()
                            await asyncio.sleep(0)

                    for frame in batch:
                        self._live_buffer.put_nowait(frame)

                    if not self._disk_queue and self._eos_written:
                        self._live_buffer.put_nowait(None)
                finally:
                    self._refilling = False
                    self._event.set()
        except asyncio.CancelledError as e:
            log_exception(e)
            return

    async def clear(self) -> None:
        """
        Clear all internal buffers and stop any operations.
        """

        self._generation += 1
        self._shutdown = True

        if self._write_task:
            self._write_queue.put_nowait(None)

            try:
                await asyncio.wait_for(self._write_task, 2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError) as e:
                log_exception(e)
                self._write_task.cancel()

                try:
                    await self._write_task
                except asyncio.CancelledError as e:
                    log_exception(e)
                    pass

                self._write_task = None

        async with self._read_lock:
            if self._read_task:
                self._read_task.cancel()

                try:
                    await self._read_task
                except asyncio.CancelledError as e:
                    log_exception(e)
                    pass

                self._read_task = None

        self._event.clear()
        self._eos_written = False
        self._eos_emitted = False
        self._refilling = False
        self._file_index = 0

        self._chunk_frame_count = 0
        self._chunk_buffer.clear()
        self._active_chunk.clear()

        self._live_buffer = asyncio.Queue()
        self._write_queue = asyncio.Queue()

        if self._connection._config.buffer.mode == BufferMode.DISK:
            while self._disk_queue:
                index: int = self._disk_queue.popleft()
                path: str = f"wavecache/{self._connection._guild_id}/{index}.wcf"

                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError as e:
                    log_exception(e)
                    pass

            try:
                cache_dir: str = f"wavecache/{self._connection._guild_id}"
                if os.path.exists(cache_dir):
                    for filename in os.listdir(cache_dir):
                        if not filename.endswith(".wcf"):
                            continue

                        try:
                            os.remove(os.path.join(cache_dir, filename))
                        except OSError as e:
                            log_exception(e)
                            pass
            except OSError as e:
                log_exception(e)
                pass

        self._shutdown = False

        if self._connection._config.buffer.mode == BufferMode.DISK:
            self._write_task = self._connection._client._tasks.create(self._disk_writer(), name="store-writer")

    async def fetch_frame(self) -> bytes | None:
        """
        Fetch the next available frame.
        """

        while True:
            if not self._live_buffer.empty():
                frame: bytes | None = self._live_buffer.get_nowait()

                if self._connection._config.buffer.mode == BufferMode.DISK and self._live_buffer.qsize() <= self._low_mark and self._disk_queue:
                    if self._read_task is None or self._read_task.done():
                        self._read_task = self._connection._client._tasks.create(self._read_chunk(), name="store-reader")

                return frame

            if self._eos_written and not self._disk_queue and not self._refilling:
                if not self._eos_emitted:
                    self._eos_emitted = True

                return None

            self._event.clear()
            await self._event.wait()

    async def store_frame(self, frame: bytes | None, generation: int) -> bool:
        """
        Store a frame.

        Parameters
        ----------
        frame : bytes | None
            The frame to store.
        generation : int
            The current source's generation ID, to prevent stale audio from extended FFmpeg processes.

        Returns
        -------
        bool
            If the frame was stored.
        """

        if generation != self._generation:
            return False

        if self._connection._config.buffer.mode == BufferMode.MEMORY:
            self._live_buffer.put_nowait(frame)
            self._event.set()
            return True

        if frame is None:
            self._eos_written = True

            if self._active_chunk:
                self._file_index += 1
                chunk_copy: bytearray = bytearray(self._active_chunk)
                self._active_chunk.clear()
                self._chunk_frame_count = 0
                self._write_queue.put_nowait((self._file_index, chunk_copy))

            if not self._disk_queue and self._write_queue.empty():
                self._live_buffer.put_nowait(None)

            self._event.set()
            return True

        has_backlog: bool = bool(self._disk_queue) or bool(self._active_chunk)

        if not has_backlog and self._live_buffer.qsize() < self._high_mark:
            self._live_buffer.put_nowait(frame)
            self._event.set()
            return True

        frame_data: bytes = len(frame).to_bytes(2, "big") + frame
        self._active_chunk.extend(frame_data)
        self._chunk_frame_count += 1

        if self._chunk_frame_count >= self._chunk_frame_limit:
            self._file_index += 1
            self._active_chunk, self._chunk_buffer = self._chunk_buffer, self._active_chunk

            self._write_queue.put_nowait((self._file_index, self._chunk_buffer))

            self._active_chunk.clear()
            self._chunk_frame_count = 0

            self._event.set()

        return True

    async def wait(self, *, frames: int = 0) -> None:
        """
        Wait until the store is available to read from.

        Parameters
        ----------
        frames : int
            If provided, the minimum amount of frames in store before continuing.
        """

        while True:
            available: int = self._live_buffer.qsize() + len(self._disk_queue)

            if available >= frames or (self._eos_written and not self._disk_queue):
                return

            self._event.clear()
            await self._event.wait()

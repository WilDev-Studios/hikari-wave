from __future__ import annotations

from collections import deque
from hikariwave.internal.constants import Audio

import aiofiles
import asyncio
import os

class FrameStore:
    def __init__(self, disk: bool, duration: int | None = None) -> None:
        self._live_buffer: asyncio.Queue[bytes | None] = asyncio.Queue()

        self._disk: bool = disk
        self._duration: int | None = duration

        self._frames_per_second: int = 1000 // Audio.FRAME_LENGTH

        self._memory_limit: int = (
            self._duration * self._frames_per_second
            if self._disk and self._duration else 0
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

        if self._disk:
            os.makedirs("wavecache", exist_ok=True)
    
    async def _flush_chunk(self) -> None:
        if not self._chunk_buffer:
            return

        self._file_index += 1

        async with aiofiles.open(f"wavecache/{self._file_index}.wcf", "wb") as file:
            await file.write(self._chunk_buffer)
        
        self._disk_queue.append(self._file_index)
        self._chunk_buffer.clear()
        self._chunk_frame_count = 0

    async def _read_chunk(self) -> None:
        async with self._read_lock:
            if self._refilling or not self._disk_queue:
                return
        
            self._refilling = True
            file_index: int = self._disk_queue.popleft()

            try:
                path: str = f"wavecache/{file_index}.wcf"

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

    async def fetch_frame(self) -> bytes | None:
        while True:
            if not self._live_buffer.empty():
                frame: bytes | bytes =  await self._live_buffer.get()
            
                if self._disk and self._live_buffer.qsize() <= self._low_mark and self._disk_queue and not self._refilling:
                    if self._read_task and not self._read_task.done():
                        self._read_task.cancel()

                    self._read_task = asyncio.create_task(self._read_chunk())
                
                return frame
            
            if self._eos_written and not self._disk_queue and not self._refilling:
                if not self._eos_emitted:
                    self._eos_emitted = True
                
                return None
            
            self._event.clear()
            await self._event.wait()

    async def store_frame(self, frame: bytes | None) -> None:
        if not self._disk:
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
        
        if self._live_buffer.qsize() < self._high_mark:
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
        if not self._live_buffer.empty() or (self._eos_written and not self._disk_queue):
            return
        
        self._event.clear()
        await self._event.wait()
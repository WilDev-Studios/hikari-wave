from __future__ import annotations

from hikariwave.internal.constants import Audio
from hikariwave.audio.source import (
    AudioSource,
    BufferAudioSource,
)
from typing import TYPE_CHECKING

import asyncio
import logging
import os
import time

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

logger: logging.Logger = logging.getLogger("hikari-wave.ffmpeg")

__all__ = ("FFmpegPool", "FFmpegWorker",)

class FFmpegWorker:
    """Manages a single FFmpeg process when requested."""

    __slots__ = ("_process",)

    def __init__(self) -> None:
        """
        Create a new worker.
        """

        self._process: asyncio.subprocess.Process = None

    async def encode(self, source: AudioSource, connection: VoiceConnection) -> None:
        """
        Encode an entire audio source and stream each Opus frame into the output.
        
        Parameters
        ----------
        source : AudioSource
            The audio source to read and encode.
        connection : VoiceConnection
            The active connection requesting this encoding.
        """

        pipeable: bool = False

        if isinstance(source, BufferAudioSource):
            content: bytearray | bytes | memoryview = source._content
            pipeable = True
        elif isinstance(source, AudioSource):
            content: str = source._content
        else:
            error: str = f"Provided audio source doesn't inherit AudioSource"
            raise TypeError(error)

        bitrate: str = source._bitrate or connection._config.bitrate
        channels: int = source._channels or connection._config.channels
        volume: float | str = source._volume or connection._config.volume

        args: list[str] = [
            "ffmpeg",
            "-blocksize", str(Audio.BLOCKSIZE),
            "-i", "pipe:0" if pipeable else content,
            "-map", "0:a",
            "-af", f"volume={volume}",
            "-acodec", "libopus",
            "-f", "opus",
            "-ar", str(Audio.SAMPLING_RATE),
            "-ac", str(channels),
            "-b:a", bitrate,
            "-application", "audio",
            "-frame_duration", str(Audio.FRAME_LENGTH),
            "-loglevel", "warning",
            "pipe:1",
        ]

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if pipeable else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        if pipeable:
            try:
                self._process.stdin.write(content)
                await self._process.stdin.drain()
                self._process.stdin.close()
                await self._process.stdin.wait_closed()
            except Exception as e:
                logger.error(f"FFmpeg encode error: {e}")
        
        start: float = time.perf_counter()
        while True:
            try:
                header: bytes = await self._process.stdout.readexactly(27)
                if not header.startswith(b"OggS"):
                    return None
                
                segments_count: int = header[26]
                segment_table: bytes = await self._process.stdout.readexactly(segments_count)

                current_packet: bytearray = bytearray()
                for lacing_value in segment_table:
                    data: bytes = await self._process.stdout.readexactly(lacing_value)
                    current_packet.extend(data)

                    if lacing_value < 255:
                        packet_bytes: bytes = bytes(current_packet)

                        if not (
                            packet_bytes.startswith(b"OpusHead") or
                            packet_bytes.startswith(b"OpusTags")
                        ):
                            await connection.player._store.store_frame(packet_bytes)
                        
                        current_packet.clear()
            except asyncio.IncompleteReadError:
                break
        
        logger.debug(f"FFmpeg finished in {(time.perf_counter() - start) * 1000:.2f}ms")

        await connection.player._store.store_frame(None)
        await self.stop()
    
    async def stop(self) -> None:
        """
        Stop the internal process.
        """
        
        if not self._process:
            return
        
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream and hasattr(stream, "_transport"):
                try:
                    stream._transport.close()
                except:
                    pass
        
        if self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

        self._process = None

class FFmpegPool:
    """Manages all FFmpeg processes and deploys them when needed."""

    __slots__ = (
        "_enabled", 
        "_max", "_total", "_min",
        "_available", "_unavailable",
    )

    def __init__(self, max_per_core: int = 2, max_global: int = 16) -> None:
        """
        Create a FFmpeg process pool.
        
        Parameters
        ----------
        max_per_core : int
            The maximum amount of processes that can be spawned per logical CPU core.
        max_global : int
            The maximum, hard-cap amount of processes that can be spawned.
        """
        
        self._enabled: bool = True

        self._max: int = min(max_global, os.cpu_count() * max_per_core)
        self._total: int = 0
        self._min: int = 0

        self._available: asyncio.Queue[FFmpegWorker] = asyncio.Queue()
        self._unavailable: set[FFmpegWorker] = set()
    
    async def submit(self, source: AudioSource, connection: VoiceConnection) -> None:
        """
        Submit and schedule an audio source to be encoded into Opus and stream output into a buffer.
        
        Parameters
        ----------
        source : AudioSource
            The audio source to read and encode.
        connection : VoiceConnection
            The active connection requesting this encoding.
        """
        
        if not self._enabled: return

        if self._available.empty() and self._total < self._max:
            worker: FFmpegWorker = FFmpegWorker()
            self._total += 1
        else:
            worker: FFmpegWorker = await self._available.get()

        self._unavailable.add(worker)

        async def _run() -> None:
            try:
                await worker.encode(source, connection)
            finally:
                self._unavailable.remove(worker)

                if self._total > self._min:
                    self._total -= 1
                else:
                    await self._available.put(worker)

        asyncio.create_task(_run())
    
    async def stop(self) -> None:
        """
        Stop future scheduling and terminate every worker process.
        """

        self._enabled = False

        await asyncio.gather(
            *(unavailable.stop() for unavailable in self._unavailable)
        )
        self._available = asyncio.Queue()
        self._unavailable.clear()

        self._total = 0
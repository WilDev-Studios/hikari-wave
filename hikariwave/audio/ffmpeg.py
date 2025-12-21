from __future__ import annotations

from hikariwave.internal.constants import Audio
from hikariwave.audio.source import (
    AudioSource,
    BufferAudioSource,
    FileAudioSource,
    URLAudioSource,
)
from hikariwave.audio.store import FrameStore
from typing import TYPE_CHECKING

import asyncio
import logging
import os
import time

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

logger: logging.Logger = logging.getLogger("hikari-wave.ffmpeg")

__all__ = ("FFmpegPool", "FFmpegWorker",)

class FFmpegWorker:
    """Manages a single FFmpeg process when requested."""

    __slots__ = ("_process", "_client",)

    def __init__(self, client: VoiceClient) -> None:
        """
        Create a new worker.

        Parameters
        ----------
        client : VoiceClient
            The voice system client application.
        """

        self._process: asyncio.subprocess.Process = None
        self._client: VoiceClient = client

    async def encode(self, source: AudioSource, output: FrameStore) -> None:
        """
        Encode an entire audio source and stream each Opus frame into the output.
        
        Parameters
        ----------
        source : AudioSource
            The audio source to read and encode.
        output : FrameStore
            The frame storage object to stream the output Opus frames into.
        """

        pipeable: bool = False

        if isinstance(source, BufferAudioSource):
            content: bytearray | bytes | memoryview = source._buffer
            pipeable = True
        elif isinstance(source, FileAudioSource):
            content: str = source._filepath
        elif isinstance(source, URLAudioSource):
            content: str = source._url
        else:
            error: str = f"Provided audio source doesn't inherit AudioSource"
            raise TypeError(error)

        volume: float | str = source._volume or 1.0

        args: list[str] = [
            "ffmpeg",
            "-i", "pipe:0" if pipeable else content,
            "-map", "0:a",
            "-af", f"volume={volume}",
            "-acodec", "libopus",
            "-f", "opus",
            "-ar", str(Audio.SAMPLING_RATE),
            "-ac", str(self._client._audio_channels),
            "-b:a", self._client._audio_bitrate,
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
                            await output.store_frame(packet_bytes)
                        
                        current_packet.clear()
            except asyncio.IncompleteReadError:
                break
        
        logger.debug(f"FFmpeg finished in {(time.perf_counter() - start) * 1000:.2f}ms")

        await output.store_frame(None)
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
        "_client", "_enabled", 
        "_max", "_total", "_min",
        "_available", "_unavailable",
    )

    def __init__(self, client: VoiceClient, max_per_core: int = 2, max_global: int = 16) -> None:
        """
        Create a FFmpeg process pool.
        
        Parameters
        ----------
        client : VoiceClient
            The voice system client application.
        max_per_core : int
            The maximum amount of processes that can be spawned per logical CPU core.
        max_global : int
            The maximum, hard-cap amount of processes that can be spawned.
        """
        
        self._client: VoiceClient = client
        self._enabled: bool = True

        self._max: int = min(max_global, os.cpu_count() * max_per_core)
        self._total: int = 0
        self._min: int = 0

        self._available: asyncio.Queue[FFmpegWorker] = asyncio.Queue()
        self._unavailable: set[FFmpegWorker] = set()
    
    async def submit(self, source: AudioSource, output: FrameStore) -> None:
        """
        Submit and schedule an audio source to be encoded into Opus and stream output into a buffer.
        
        Parameters
        ----------
        source : AudioSource
            The audio source to read and encode.
        output : FrameStore
            The frame storage object to stream the output Opus frames into.
        """
        
        if not self._enabled: return

        if self._available.empty() and self._total < self._max:
            worker: FFmpegWorker = FFmpegWorker(self._client)
            self._total += 1
        else:
            worker: FFmpegWorker = await self._available.get()

        self._unavailable.add(worker)

        async def _run() -> None:
            try:
                await worker.encode(source, output)
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
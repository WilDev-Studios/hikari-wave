from __future__ import annotations

from hikariwave.internal.constants import Audio
from hikariwave.audio.source import (
    AudioSource,
    BufferAudioSource,
    YouTubeAudioSource,
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
        headers: str | None = None

        if isinstance(source, BufferAudioSource):
            content: bytearray | bytes | memoryview = source._content
            pipeable = True
        elif isinstance(source, YouTubeAudioSource):
            content: str = await source.wait_for_url()

            if source._headers:
                headers = YouTubeAudioSource._format_headers(source._headers)
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
            "-loglevel", "warning",
        ]

        if headers:
            args.extend(["-headers", headers])

        args.extend([
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
            "pipe:1",
        ])

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if pipeable else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if pipeable:
            try:
                self._process.stdin.write(content)
                await self._process.stdin.drain()
                self._process.stdin.close()
                await self._process.stdin.wait_closed()
            except Exception as e:
                logger.error(f"FFmpeg encode error: {e}")
        
        async def read_stderr() -> list[str]:
            output: list[str] = []

            try:
                while True:
                    line: bytes = await self._process.stderr.readline()
                    if not line:
                        break

                    decoded: str = line.decode("utf-8", "replace").strip()
                    if decoded:
                        output.append(decoded)
                        logger.warning(f"FFmpeg stderr: {decoded}")
            except Exception as e:
                logger.error(f"Error reading stderr: {e}")
            
            return output

        stderr_task: asyncio.Task[list[str]] = asyncio.create_task(read_stderr())

        start: float = time.perf_counter()
        frame_count: int = 0
        try:
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
                                frame_count += 1
                            
                            current_packet.clear()
                except asyncio.IncompleteReadError:
                    break
        except Exception as e:
            logger.error(f"FFmpeg processing error: {e}")
            raise

        stderr_output: list[str] = await stderr_task
        
        logger.debug(f"FFmpeg finished in {(time.perf_counter() - start) * 1000:.2f}ms")

        if frame_count == 0 and stderr_output:
            error: str = "\n".join(stderr_output[-10:])
            logger.error(f"FFmpeg failed to produce any frames. STDERR:\n{error}")
            
            error = f"FFmpeg encoding failed: {error}"
            raise RuntimeError(error)
        
        await self._process.wait()
        if self._process.returncode != 0:
            error_msg: str = "\n".join(stderr_output[-10:]) if stderr_output else "No error output"
            error: str = f"FFmpeg exited with code {self._process.returncode}: {error_msg}"
            raise RuntimeError(error)

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
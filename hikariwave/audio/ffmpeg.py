from __future__ import annotations

from hikariwave.internal.constants import Audio
from hikariwave.audio.source import (
    AudioSource,
    BufferAudioSource,
    YouTubeAudioSource,
)
from typing import TYPE_CHECKING

import asyncio
import contextlib
import logging
import os

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

logger: logging.Logger = logging.getLogger("hikari-wave.ffmpeg")

__all__ = ()

class _StaleEncode(Exception):...

class FFmpegProcess:
    """FFmpeg encoder process."""

    __slots__ = ("_process",)

    def __init__(self) -> None:
        """
        Create a new FFmpeg process handler.
        """
        
        self._process: asyncio.subprocess.Process = None
    
    async def start(self, args: list[str], *, stdin: bool) -> asyncio.subprocess.Process:
        """
        Start the internal process.
        
        Parameters
        ----------
        args : list[str]
            The arguments to pass to the FFmpeg process.
        stdin : bool
            If `STDIN` should be pipeable.
        
        Returns
        -------
        asyncio.subprocess.Process
            The internal, active process.
        """

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if stdin else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return self._process
    
    async def terminate(self) -> None:
        """
        Kill the internal process.
        """

        if not self._process:
            return
        
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if not stream or not hasattr(stream, "_transport"):
                continue

            with contextlib.suppress(Exception):
                stream._transport.close()
        
        if self._process.returncode is None:
            self._process.terminate()

            try:
                await asyncio.wait_for(self._process.wait(), 1.5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        
        self._process = None

class FFmpegWorker:
    """Manages a single FFmpeg process when requested."""

    __slots__ = ("_process",)

    def __init__(self) -> None:
        """
        Create a new worker.
        """

        self._process: FFmpegProcess = FFmpegProcess()

    async def _encode(self, source: AudioSource, connection: VoiceConnection) -> None:
        try:
            generation: int = connection._player._store._generation

            pipeable: bool = isinstance(source, BufferAudioSource)
            headers: str | None = None

            if isinstance(source, BufferAudioSource):
                content: bytearray | bytes | memoryview = source._content
            elif isinstance(source, YouTubeAudioSource):
                content: str = await source.resolve_media()

                if source._headers:
                    headers = "".join(f"{k}: {v}\r\n" for k, v in source._headers.items())
            elif isinstance(source, AudioSource):
                content: str = getattr(source, "_content")

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

            process: asyncio.subprocess.Process = await self._process.start(args, stdin=pipeable)
            stdin_task: asyncio.Task[None] = None

            if pipeable:
                stdin_task = asyncio.create_task(self._write_stdin(process.stdin, content))
            
            stderr_task: asyncio.Task[None] = asyncio.create_task(self._drain_stderr(process.stderr))

            try:
                await self._read_frames(process.stdout, connection, generation)
            except _StaleEncode:
                logger.debug(f"FFmpeg encode became stale; terminating process...")
                await self._process.terminate()
                return

            if stdin_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await stdin_task
            
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            
            if generation == connection._player._store._generation:
                await connection._player._store.store_frame(None, generation)
            
            await self._process.terminate()
        except asyncio.CancelledError:
            logger.debug("FFmpeg encode cancelled; terminating process")

            if stdin_task:
                stdin_task.cancel()
            
            stderr_task.cancel()

            await self._process.terminate()
            raise

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        while await stderr.readline():
            pass

    async def _flush_frames(self, frames: list[bytes], connection: VoiceConnection, generation: int) -> None:
        for frame in frames:
            stored: bool = await connection._player._store.store_frame(frame, generation)

            if not stored:
                raise _StaleEncode()

    async def _read_frames(self, stdout: asyncio.StreamReader, connection: VoiceConnection, generation: int) -> None:
        frames: list[bytes] = []
        BATCH_SIZE: int = 50

        while True:
            if generation != connection._player._store._generation:
                raise _StaleEncode()
            
            try:
                header: bytes = await stdout.readexactly(27)
                if not header.startswith(b"OggS"):
                    break

                segments: bytes = header[26]
                lacing: bytes = await stdout.readexactly(segments)

                packet: bytearray = bytearray()
                for size in lacing:
                    packet.extend(await stdout.readexactly(size))

                    if size >= 255:
                        continue

                    if packet.startswith(b"OpusHead") or packet.startswith(b"OpusTags"):
                        continue

                    frames.append(bytes(packet))

                    if len(frames) >= BATCH_SIZE:
                        await self._flush_frames(frames, connection, generation)
                        frames.clear()
                    
                    packet.clear()
            except asyncio.IncompleteReadError:
                break
        
        if frames:
            await self._flush_frames(frames, connection, generation)

    async def _write_stdin(self, stdin: asyncio.StreamWriter, content: bytes) -> None:
        CHUNK_SIZE: int = 65536
        for i in range(0, len(content), CHUNK_SIZE):
            stdin.write(content[i:i + CHUNK_SIZE])

            if i % (CHUNK_SIZE * 10) == 0:
                await stdin.drain()
        
        await stdin.drain()
        stdin.close()
        await stdin.wait_closed()

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

        MAX_RETRIES: int = 3
        last_error: Exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if attempt == MAX_RETRIES and isinstance(source, YouTubeAudioSource):
                    await source.resolve_media(True)
                    
                return await self._encode(source, connection)
            except RuntimeError as e:
                last_error = e

                logger.debug(f"FFmpeg encode failed (attempt {attempt} / {MAX_RETRIES}).{' Retrying' if attempt < MAX_RETRIES else ''}")

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue

                break
        
        logger.error(f"FFmpeg failed after retries; media URL likely expired")

        error: str = "Media URL expired or unavailable. Please regenerate the audio source"
        raise RuntimeError(error) from last_error

    async def stop(self) -> None:
        """
        Stop the internal process.
        """
        
        await self._process.terminate()

class FFmpegPool:
    """Manages all FFmpeg workers and deploys them when needed."""

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
            except Exception:
                pass
            finally:
                self._unavailable.remove(worker)

                if self._total > self._min:
                    self._total -= 1
                else:
                    await self._available.put(worker)

        encoder: asyncio.Task[None] = asyncio.create_task(_run())
        connection._player._encoders.add(encoder)
        encoder.add_done_callback(connection._player._encoders.discard)

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
from __future__ import annotations

from collections import deque
from hikariwave.constants import Audio

import asyncio
import logging

logger: logging.Logger = logging.getLogger("hikariwave.ffmpeg")

class FFmpeg:
    """Handles both decoding audio to PCM and encoding to Opus using FFmpeg."""

    def __init__(self) -> None:
        """
        Create a new FFmpeg audio handler.
        """
        
        self._process: asyncio.subprocess.Process = None
        self._queue: deque[bytes] = deque()
    
    async def read(self) -> bytes | None:
        """
        Read the next Opus packet from the FFmpeg audio stream.
        
        Returns
        -------
        bytes | None
            The Opus packet, if present.
        """

        if self._queue:
            return self._queue.popleft()

        if not self._process or not self._process.stdout or self._process.stdout.at_eof():
            return None
        
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
                        self._queue.append(packet_bytes)
                    
                    current_packet.clear()
            
            return self._queue.popleft() if self._queue else await self.read()
        except asyncio.IncompleteReadError | AttributeError | IndexError:
            return None

    async def start(self, raw: bytes | str) -> None:
        """
        Start the (en/de)coding process of an input.
        """
        
        await self.stop()
        
        args: list[str] = [
            "ffmpeg",
            "-i", "pipe:0" if isinstance(raw, bytes) else raw,
            "-map", "0:a",
            "-acodec", "libopus",
            "-f", "opus",
            "-ar", str(Audio.SAMPLING_RATE),
            "-ac", str(Audio.CHANNELS),
            "-b:a", "96k",
            "-application", "audio",
            "-frame_duration", str(Audio.FRAME_LENGTH),
            "-loglevel", "warning",
            "pipe:1",
        ]

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if isinstance(raw, bytes) else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        if isinstance(raw, bytes):
            try:
                self._process.stdin.write(raw)
                await self._process.stdin.drain()
                self._process.stdin.close()
                await self._process.stdin.wait_closed()
            except:
                pass
    
    async def stop(self) -> None:
        """
        Terminate the FFmpeg process.
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
        self._queue.clear()
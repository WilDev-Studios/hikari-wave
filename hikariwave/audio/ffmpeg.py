from __future__ import annotations

from hikariwave.constants import Audio

import asyncio
import logging

logger: logging.Logger = logging.getLogger("hikariwave.ffmpeg")

class FFmpegDecoder:
    """Decodes audio into PCM frames."""

    def __init__(self) -> None:
        """
        Create a new FFmpeg decoder.
        """
        
        self._process: asyncio.subprocess.Process = None
    
    async def decode(self, size: int) -> bytes:
        """
        Decode the audio into PCM.

        Parameters
        ----------
        size : int
            The amount of audio to return.
        
        Returns
        -------
        bytes | None
            The decoded PCM audio.
        """

        if not self._process: return
        return await self._process.stdout.read(size)

    async def start(self, raw: bytes | str) -> None:
        """
        Start FFmpeg decoding audio.
        
        Parameters
        ----------
        raw : bytes | str
            The raw audio data or filepath.
        """

        if self._process:
            await self.stop()
        
        if isinstance(raw, bytes):
            self._process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i", "pipe:0",
                "-f", "s16le",
                "-ar", str(Audio.SAMPLING_RATE),
                "-ac", str(Audio.CHANNELS),
                "-loglevel", "warning",
                "-blocksize", str(Audio.BLOCKSIZE),
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )

            self._process.stdin.write(raw)
            await self._process.stdin.drain()
            self._process.stdin.close()
            await self._process.stdin.wait_closed()
        else:
            self._process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i", raw,
                "-f", "s16le",
                "-ar", str(Audio.SAMPLING_RATE),
                "-ac", str(Audio.CHANNELS),
                "-loglevel", "warning",
                "-blocksize", str(Audio.BLOCKSIZE),
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
            )
    
    async def stop(self) -> None:
        """
        Stop the decoding of audio.
        """
        
        if not self._process:
            return
        
        try:
            if self._process.stdin and not self._process.stdin.is_closing():
                try:
                    self._process.stdin.close()
                    await self._process.stdin.wait_closed()
                except:...
            
            if self._process.returncode is None:
                self._process.terminate()

                try:
                    await asyncio.wait_for(self._process.wait(), 0.5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:...
        except Exception as e:
            logger.debug(f"Error stopping FFmpeg: {e}")
        finally:
            self._process = None
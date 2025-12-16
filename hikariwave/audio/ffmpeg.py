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
        
        self.process: asyncio.subprocess.Process = None
    
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

        if not self.process: return
        return await self.process.stdout.read(size)

    async def start(self, raw: bytes | str) -> None:
        """
        Start FFmpeg decoding audio.
        
        Parameters
        ----------
        raw : bytes | str
            The raw audio data or filepath.
        """

        if self.process:
            await self.stop()
        
        if isinstance(raw, bytes):
            self.process = await asyncio.create_subprocess_exec(
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

            self.process.stdin.write(raw)
            await self.process.stdin.drain()
            self.process.stdin.close()
            await self.process.stdin.wait_closed()
        else:
            self.process = await asyncio.create_subprocess_exec(
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
        
        if not self.process:
            return
        
        try:
            if self.process.stdin and not self.process.stdin.is_closing():
                try:
                    self.process.stdin.close()
                    await self.process.stdin.wait_closed()
                except:...
            
            if self.process.stdout and not self.process.stdout.at_eof():
                try:
                    self.process.stdout.feed_eof()
                except:...
            
            if self.process.returncode is None:
                self.process.terminate()

                try:
                    await asyncio.wait_for(self.process.wait(), 0.5)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        except ProcessLookupError:...
        except Exception as e:
            logger.debug(f"Error stopping FFmpeg: {e}")
        finally:
            self.process = None
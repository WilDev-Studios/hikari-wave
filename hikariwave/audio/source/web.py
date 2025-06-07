from __future__ import annotations

import aiohttp
import asyncio

from hikariwave.audio.source.base import AudioSource
from hikariwave.internal import constants
from typing import AsyncGenerator
from typing_extensions import override


class WebAudioSource(AudioSource):
    """
    Web-based audio source implementation.

    Warning
    -------
    This is an internal object and should not be instantiated.
    """

    def __init__(self, url: str) -> None:
        """
        Create a new web audio source.

        Warning
        -------
        This is an internal method and should not be called.

        Parameters
        ----------
        url : str
            The URL of an audio file.
        """
        self._url: str = url

    @override
    async def decode(self) -> AsyncGenerator[bytes, None]: # type: ignore
        async with aiohttp.ClientSession() as session:
            async with session.get(self._url) as response:
                if response.status != 200:
                    error: str = f"Failed to fetch audio: HTTP {response.status}"
                    raise RuntimeError(error)

                ffmpeg: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-i",
                    "pipe:0",
                    "-f",
                    str(constants.PCM_FORMAT),
                    "-ar",
                    str(constants.SAMPLE_RATE),
                    "-ac",
                    str(constants.CHANNELS),
                    "pipe:1",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )

                async def feed_ffmpeg() -> None:
                    async for chunk in response.content.iter_chunked(1024 * 16):
                        if not chunk or not ffmpeg.stdin:
                            break

                        ffmpeg.stdin.write(chunk)
                        await ffmpeg.stdin.drain()

                    if ffmpeg.stdin:
                        ffmpeg.stdin.close()

                asyncio.create_task(feed_ffmpeg())

                while ffmpeg.stdout:
                    pcm: bytes = await ffmpeg.stdout.read(
                        constants.FRAME_SIZE * constants.CHANNELS * 2,
                    )

                    if not pcm:
                        break

                    yield pcm

                await ffmpeg.wait()

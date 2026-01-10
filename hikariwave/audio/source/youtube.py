from __future__ import annotations

from hikariwave.audio.source.base import (
    AudioSource,
    validate_content,
    validate_name,
)
from hikariwave.config import (
    validate_bitrate,
    validate_channels,
    validate_volume,
)
from yt_dlp.YoutubeDL import YoutubeDL as YT

import asyncio

__all__ = ("YouTubeAudioSource",)

class YouTubeAudioSource(AudioSource):
    """YouTube audio source implementation."""

    __slots__ = (
        "_url",
        "_bitrate",
        "_channels",
        "_duration",
        "_name",
        "_volume",
        "_content",
        "_headers",
        "_metadata",
        "_future",
    )

    def __init__(
        self,
        url: str,
        *,
        bitrate: str | None = None,
        channels: int | None = None,
        name: str | None = None,
        volume: float | str | None = None
    ) -> None:
        """
        Create a YouTube audio source.
        
        Parameters
        ----------
        url : str
            The YouTube URL of the audio source.
        bitrate : str | None
            If provided, the bitrate in which to play this source back at.
        channels : int | None
            If provided, the amount of channels this source plays with.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        
        Important
        ---------
        This source resolves the provided YouTube URL into an internal, direct media URL using `yt-dlp`.
        This resolution is performed asynchronously in the background during construction.

        The resolved media URL may not be immediately available after instantiation. Consumers that require guaranteed availability should `await` the source's completion mechanism (e.g. `await source.wait_for_url()`).

        This source depends on YouTube's undocumented internal APIs via `yt-dlp`. As a result, it is best-effort and may break without notice if YouTube changes its internal behavior.
        Functionality may require updating the pinned `yt-dlp` version to restore compatibility.

        Raises
        ------
        TypeError
            - If `url` is not `str`.
            - If `bitrate` is provided and not `str`.
            - If `channels` is provided and not `int`.
            - If `name` is provided and not `str`.
            - If `volume` is provided and not `float` or `str`.
        ValueError
            - If `url` is empty.
            - If `bitrate` is provided, and is not between `6k` and `510k`.
            - If `channels` is provided and not `1` or `2`.
            - If `name` is provided and is empty.
            - If `volume` is provided and is either a `float` and is not positive or a `str` and does not end with `dB`, contain a number, or (if provided) doesn't begin with `-` or `+`.
        """

        self._url: str = validate_content(url, "url", (str,))

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

        self._content: str | None = None
        self._duration: float | None = None
        self._headers: dict[str, str] = {}
        self._metadata: dict[str] = {}

        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self._future: asyncio.Task[None] = loop.create_task(self._extract_metadata(loop))

    async def _extract_metadata(self, loop: asyncio.AbstractEventLoop) -> None:
        def extract() -> None:
            with YT({
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "simulate": True,
                "noplaylist": True,
                "extract_flat": True,
                "http_headers": {},
                "force_generic_extractor": False,
                "http2": True,
                "writesubtitles": False,
                "writeautomaticsub": False,
                "writeinfojson": False,
                "skip_download": True,
            }) as ydl:
                self._metadata = ydl.extract_info(self._url, False)
                self._content = self._metadata["url"]
                self._headers = self._metadata.get("http_headers", {})
                self._duration = self._metadata.get("duration")

        await loop.run_in_executor(None, extract)

    @staticmethod
    def _format_headers(headers: dict[str, str]) -> str:
        return "".join(f"{k}: {v}\r\n" for k, v in headers.items())

    @property
    def duration(self) -> float | None:
        """The duration of the media source URL, if discovered - Wait for the source `future` property to finish to attain."""
        return self._duration

    @property
    def metadata(self) -> dict[str, str]:
        """The metadata of the YouTube media provided, if discovered - Wait for the source `future` property to finish to attain."""
        return self._metadata.copy()

    @property
    def future(self) -> asyncio.Task[None]:
        """The future that will be completed when the internal media URL is discovered."""
        return self._future

    @property
    def url_media(self) -> str | None:
        """The media source URL that the YouTube URL points to, if discovered - Wait for the source `future` property to finish to attain."""
        return self._content

    @property
    def url_youtube(self) -> str:
        """The URL to the audio source."""
        return self._url
    
    async def wait_for_url(self) -> str:
        """Waits for extraction of the internal media URL, if needed, then returns that URL."""
        if self._content is None:
            await self._future
        
        return self._content
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
from typing import TYPE_CHECKING
from yt_dlp.YoutubeDL import YoutubeDL as YT

import asyncio

if TYPE_CHECKING:
    from typing import Any

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
        volume: float | str | None = None,
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
        This source depends on YouTube's undocumented internal APIs via `yt-dlp`. As a result, it is best-effort and may break without notice if YouTube changes its internal behavior.
        Functionality may require updating the pinned `yt-dlp` version to restore compatibility.

        Basic video metadata is extracted on construction of this source. Using `resolve_metadata` will ensure this metadata is retrieved before using the `metadata` property.
        Enhanced video metadata, like media URLs, is extracted on request internally by the player (to ensure non-expired timestamps and nonces). Using `resolve_media` does this as well.

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

        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._metadata_task: asyncio.Task[None] | None = loop.create_task(self._extract_metadata())

        self._media_task: asyncio.Task[None] | None = None

    async def _extract_media(self) -> None:
        def extract() -> dict[str, Any]:
            with YT({
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio",
                "noplaylist": True,
            }) as ydl:
                return ydl.extract_info(self._url, False)
        
        info: dict[str, Any] = await asyncio.to_thread(extract)

        self._content = info["url"]
        self._headers = info.get("http_headers", {})

    async def _extract_metadata(self) -> None:
        def extract() -> dict[str, Any]:
            with YT({
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "simulate": True,
                "skip_download": True,
                "noplaylist": True,
            }) as ydl:
                return ydl.extract_info(self._url, False)

        info: dict[str, Any] = await asyncio.to_thread(extract)

        self._metadata = info
        self._duration = info.get("duration")

    @property
    def duration(self) -> float | None:
        """The duration of the media source URL, if discovered - Use `resolve_metadata` or `resolve_media` to attain if not discovered."""
        return self._duration

    @property
    def metadata(self) -> dict[str, Any]:
        """The metadata of the YouTube media provided, if discovered - Use `resolve_metadata` or `resolve_media` to attain if not discovered."""
        return self._metadata.copy()

    async def resolve_media(self, force: bool = False) -> str:
        """
        Resolve the video's media URL and enhanced metadata.
        
        Parameters
        ----------
        force : bool
            If already previously resolved, re-resolve and overwrite the metadata.

        Returns
        -------
        str
            The internal video media URL used for playback.
        """

        if self._content:
            return self.url_media
        
        if self._media_task:
            await self._media_task
            return self.url_media
        
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self._media_task = loop.create_task(self._extract_media())
        await self._media_task

        return self.url_media

    async def resolve_metadata(self) -> dict[str, Any]:
        """
        Resolve the video's basic metadata.
        
        Returns
        -------
        dict[str, Any]
            The metadata of this video, once discovered.
        """
        
        if self._metadata:
            return self.metadata
        
        if self._metadata_task:
            await self._metadata_task
            return self.metadata
        
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._metadata_task = loop.create_task(self._extract_metadata())
        await self._metadata_task

        return self.metadata

    @property
    def url_media(self) -> str | None:
        """The media source URL that the YouTube URL points to, if discovered - Use `resolve_media` to attain if not discovered."""
        return self._content

    @property
    def url_youtube(self) -> str:
        """The URL to the audio source."""
        return self._url
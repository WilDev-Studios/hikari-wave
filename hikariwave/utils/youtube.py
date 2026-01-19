from __future__ import annotations

from typing import TYPE_CHECKING
from yt_dlp.YoutubeDL import YoutubeDL as YT

import asyncio

if TYPE_CHECKING:
    from typing import Any

__all__ = (
    "YouTube",
    "YouTubePartialVideo",
    "YouTubeSearchResult",
    "YouTubeThumbnail",
)

class YouTubeThumbnail:
    """YouTube thumbnail data."""

    __slots__ = (
        "_height",
        "_url",
        "_width",
    )

    def __init__(self, data: dict[str, str | int]) -> None:
        """
        Create a new thumbnail container.
        
        Parameters
        ----------
        data : dict[str, str | int]
            The raw thumbnail data.
        """

        self._height: int = int(data.get("height", 0))
        self._url: str = str(data.get("url"))
        self._width: int = int(data.get("width", 0))

    def __repr__(self) -> str:
        return f"YouTubeThumbnail(height={self._height}, width={self._width}, url={self._url})"

    @property
    def height(self) -> int:
        """The height of this thumbnail in pixels."""
        return self._height
    
    @property
    def url(self) -> str:
        """The media URL of this thumbnail."""
        return self._url
    
    @property
    def width(self) -> int:
        """The width of this thumbnail in pixels."""
        return self._width

class YouTubePartialVideo:
    """Partial YouTube video data."""

    __slots__ = (
        "_channel",
        "_channel_id",
        "_description",
        "_duration",
        "_id",
        "_thumbnail",
        "_thumbnails",
        "_timestamp",
        "_title",
        "_url",
        "_view_count",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        """
        Create a new partial YouTube video container.
        
        Parameters
        ----------
        data : dict[str, Any]
            The raw video data.
        """
        
        for key, value in data.items():
            if key == "thumbnails":
                value = [YouTubeThumbnail(thumbnail) for thumbnail in value]

            try:
                setattr(self, f"_{key}", value)
            except AttributeError:
                continue

    def __repr__(self) -> str:
        return f"YouTubePartialVideo(title={self.title!r}, url={self.url!r})"

    @property
    def channel(self) -> str | None:
        """The name of the channel that uploaded the video, if provided."""
        return getattr(self, "_channel", None)
    
    @property
    def channel_id(self) -> str | None:
        """The ID of the channel that uploaded the video, if provided."""
        return getattr(self, "_channel_id", None)
    
    @property
    def description(self) -> str | None:
        """The description of the video, if provided."""
        return getattr(self, "_description", None)

    @property
    def duration(self) -> float | None:
        """The duration of the video in seconds, if provided."""
        return getattr(self, "_duration", None)

    @property
    def id(self) -> str | None:
        """The ID of the video, if provided."""
        return getattr(self, "_id", None)

    @property
    def thumbnail(self) -> str | None:
        """The URL of the primary thumbnail of the video, if provided."""
        return getattr(self, "_thumbnail", self.thumbnails[0].url if self.thumbnails else None)
    
    @property
    def thumbnails(self) -> list[YouTubeThumbnail]:
        """A collection of all video thumbnails, if provided."""
        return getattr(self, "_thumbnails", [])
    
    @property
    def timestamp(self) -> int | None:
        """The time in which this video was uploaded, if provided."""
        return getattr(self, "_timestamp", None)
    
    @property
    def title(self) -> str:
        """The title of the video."""
        return self._title
    
    @property
    def url(self) -> str:
        """The URL of the video page."""
        return self._url

    @property
    def view_count(self) -> int | None:
        """The amount of views this video has, if provided."""
        return getattr(self, "_view_count", None)

class YouTubeSearchResult:
    """Result of a YouTube search."""

    __slots__ = (
        "_query",
        "_raw",
        "_videos",
    )

    def __init__(self, query: str, data: dict[str, Any]) -> None:
        """
        Create a new YouTube search result.
        
        Parameters
        ----------
        query: str
            The query used to search YouTube.
        data : dict[str, Any]
            The raw data passed from `yt-dlp`'s search query.
        """

        self._query: str = query
        self._raw: dict[str, Any] = data
        self._videos: list[YouTubePartialVideo] = []

        entries: list[dict[str, Any]] = data.get("entries", [])
        for entry in entries:
            if not entry:
                continue

            url: str = entry.get("webpage_url") or entry.get("url")
            if not url:
                continue

            if entry.get("age_limit", 0) >= 18:
                continue

            self._videos.append(YouTubePartialVideo(entry))

    @property
    def query(self) -> str:
        """The search query resulting in this result."""
        return self._query
    
    @property
    def raw(self) -> dict[str, Any]:
        """The raw data from the query request."""
        return self._raw
    
    @property
    def videos(self) -> list[YouTubePartialVideo]:
        """The parsed video data from the query request."""
        return self._videos

class _YouTubeInternal:
    @staticmethod
    def search(query: str, limit: int) -> YouTubeSearchResult | None:
        if not isinstance(query, str):
            error: str = "Provided query must be `str`"
            raise TypeError(error)
        
        if not isinstance(limit, int):
            error: str = "Provided limit must be `int`"
            raise TypeError(error)
        
        if not query:
            error: str = "Provided query length must be at least `1`"
            raise ValueError(error)
        
        if limit < 1:
            error: str = "Provided limit must be at least `1`"
            raise ValueError(error)

        with YT({"extract_flat": True, "skip_download": True, "quiet": True,}) as ydl:
            info: dict[str, Any] = ydl.extract_info(f"ytsearch{limit}:{query}", False)

        if not info:
            return None
        
        return YouTubeSearchResult(query, info)

class YouTube:
    """Utility class containing UX features for `YouTube`."""

    @staticmethod
    async def search(query: str, limit: int = 10) -> YouTubeSearchResult | None:
        """
        Asynchronously search YouTube via a query.
        
        Parameters
        ----------
        query : str
            The keywords/query to search YouTube with.
        limit : int
            The maximum amount of results to return.
        
        Returns
        -------
        YouTubeSearchResult
            The resulting search from the query, if successful.
        
        Raises
        ------
        TypeError
            - If `query` is not a `str`.
            - If `limit` is provided and not `int`.
        ValueError
            - If `query` length is less than `1`.
            - If `limit` is less than `1`.
        """

        return await asyncio.to_thread(_YouTubeInternal.search, query, limit)
    
    @staticmethod
    def search_sync(query: str, limit: int = 10) -> YouTubeSearchResult | None:
        """
        Synchronously search YouTube via a query.
        
        Parameters
        ----------
        query : str
            The keywords/query to search YouTube with.
        limit : int
            The maximum amount of results to return.
        
        Returns
        -------
        YouTubeSearchResult
            The resulting search from the query, if successful.
        
        Raises
        ------
        TypeError
            - If `query` is not a `str`.
            - If `limit` is provided and not `int`.
        ValueError
            - If `query` length is less than `1`.
            - If `limit` is less than `1`.
        """

        return _YouTubeInternal.search(query, limit)
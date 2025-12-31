from __future__ import annotations

from hikariwave.config import (
    validate_bitrate,
    validate_channels,
    validate_volume,
)
from yt_dlp.YoutubeDL import YoutubeDL as YT

import asyncio
import os

__all__ = (
    "AudioSource",
    "BufferAudioSource",
    "FileAudioSource",
    "URLAudioSource",
    "YouTubeAudioSource",
)

def _validate_content(content: object, name: str, expected: tuple[object]) -> type:
    if not isinstance(content, expected):
        if len(expected) == 1:
            error: str = f"Provided {name} must be `{expected}`"
        elif len(expected) == 2:
            error: str = f"Provided {name} must be `{expected[0]}` or `{expected[1]}`"
        else:
            types: list[str] = [f"`{type_.__name__}`" for type_ in expected]
            error: str = f"Provided {name} must be " + ", ".join(types[:-1]) + f", or {types[-1]}"
        
        raise TypeError(error)
    
    try:
        if len(content) == 0:
            error: str = f"Provided {name} can't be empty"
            raise ValueError(error)
    except TypeError:
        pass

    return content

def _validate_name(name: object) -> str:
    if not isinstance(name, str):
        error: str = "Provided name must be `str`"
        raise TypeError(error)
    
    if len(name) == 0:
        error: str = "Provided name cannot be empty"
        raise ValueError(error)
    
    return name

class AudioSource:
    """Base audio source implementation."""

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other): return False
        return self._content == other._content
    
    def __hash__(self) -> int:
        return hash((type(self), self._content))

    @property
    def bitrate(self) -> str | None:
        """If provided, the bitrate in which this source is played back at."""
        return self._bitrate

    @property
    def channels(self) -> int | None:
        """If provided, the amount of channels this source plays with."""
        return self._channels
    
    @property
    def name(self) -> str | None:
        """If provided, the name assigned to this source for display purposes."""
        return self._name

    @property
    def volume(self) -> float | str | None:
        """If provided, the overriding volume for this source."""
        return self._volume

class BufferAudioSource(AudioSource):
    """Buffered audio source implementation."""

    __slots__ = (
        "_content",
        "_bitrate",
        "_channels",
        "_name",
        "_volume",
    )

    def __init__(
        self,
        buffer: bytearray | bytes | memoryview,
        *,
        bitrate: str | None = None,
        channels: int | None = None,
        name: str | None = None,
        volume: float | str | None = None
    ) -> None:
        """
        Create a buffered audio source.
        
        Parameters
        ----------
        buffer : bytearray | bytes | memoryview
            The audio data as a buffer.
        bitrate : str | None
            If provided, the bitrate in which to play this source back at.
        channels : int | None
            If provided, the amount of channels this source plays with.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        
        Raises
        ------
        TypeError
            - If `buffer` is not `bytearray`, `bytes`, or `memoryview`.
            - If `bitrate` is provided and not `str`.
            - If `channels` is provided and not `int`.
            - If `name` is provided and not `str`.
            - If `volume` is provided and not `float` or `str`.
        ValueError
            - If `buffer` is empty.
            - If `bitrate` is provided, and is not between `6k` and `510k`.
            - If `channels` is provided and not `1` or `2`.
            - If `name` is provided and is empty.
            - If `volume` is provided and is either a `float` and is not positive or a `str` and does not end with `dB`, contain a number, or (if provided) doesn't begin with `-` or `+`.
        """

        self._content: bytearray | bytes | memoryview = _validate_content(
            buffer,
            "buffer",
            (bytearray, bytes, memoryview)
        )

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = _validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None
    
    @property
    def buffer(self) -> bytearray | bytes | memoryview:
        """The audio data as a buffer."""
        return self._content

class FileAudioSource(AudioSource):
    """File audio source implementation."""

    __slots__ = (
        "_content",
        "_bitrate",
        "_channels",
        "_name",
        "_volume",
    )

    def __init__(
        self,
        filepath: str,
        *,
        bitrate: str | None = None,
        channels: int | None = None,
        name: str | None = None,
        volume: float | str | None = None
    ) -> None:
        """
        Create a file audio source.
        
        Parameters
        ----------
        filepath : str
            The filepath to the audio file.
        bitrate : str | None
            If provided, the bitrate in which to play this source back at.
        channels : int | None
            If provided, the amount of channels this source plays with.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        
        Raises
        ------
        TypeError
            - If `filepath` is not `str`.
            - If `bitrate` is provided and not `str`.
            - If `channels` is provided and not `int`.
            - If `name` is provided and not `str`.
            - If `volume` is provided and not `float` or `str`.
        ValueError
            - If `filepath` is empty or is not found as a file on the system.
            - If `bitrate` is provided, and is not between `6k` and `510k`.
            - If `channels` is provided and not `1` or `2`.
            - If `name` is provided and is empty.
            - If `volume` is provided and is either a `float` and is not positive or a `str` and does not end with `dB`, contain a number, or (if provided) doesn't begin with `-` or `+`.
        """

        self._content: str = _validate_content(filepath, "filepath", (str,))

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = _validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

        if not os.path.isfile(self._content):
            error: str = f"No file exists at this path: {self._content}"
            raise FileNotFoundError(error)
    
    @property
    def filepath(self) -> str:
        """The filepath to the audio file"""
        return self._content

class URLAudioSource(AudioSource):
    """URL audio source implementation."""

    __slots__ = (
        "_content",
        "_bitrate",
        "_channels",
        "_name",
        "_volume",
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
        Create a URL audio source.
        
        Parameters
        ----------
        url : str
            The URL to the audio source.
        bitrate : str | None
            If provided, the bitrate in which to play this source back at.
        channels : int | None
            If provided, the amount of channels this source plays with.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        
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

        self._content: str = _validate_content(url, "url", (str,))

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = _validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

    @property
    def url(self) -> str:
        """The URL to the audio source."""
        return self._content

class YouTubeAudioSource(AudioSource):
    """YouTube audio source implementation."""

    __slots__ = (
        "_url",
        "_bitrate",
        "_channels",
        "_name",
        "_volume",
        "_content",
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

        self._url: str = _validate_content(url, "url", (str,))

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = _validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

        self._content: str | None = None

        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self._future: asyncio.Task[str] = loop.create_task(self._extract_url(loop))

    async def _extract_url(self, loop: asyncio.AbstractEventLoop) -> str:
        def extract() -> str:
            with YT({"quiet": True, "no_warnings": True, "format": "bestaudio[ext=m4a]/bestaudio/best"}) as ydl:
                return ydl.extract_info(self._url, False)["url"]
            
        self._content = await loop.run_in_executor(None, extract)
        return self._content

    @property
    def future(self) -> asyncio.Task[str]:
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
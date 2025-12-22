from __future__ import annotations

from hikariwave.config import (
    validate_bitrate,
    validate_channels,
    validate_volume,
)

import os

__all__ = (
    "AudioSource",
    "BufferAudioSource",
    "FileAudioSource",
    "URLAudioSource",
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
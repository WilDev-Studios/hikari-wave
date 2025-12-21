from __future__ import annotations

from abc import ABC, abstractmethod

import os

__all__ = (
    "AudioSource",
    "BufferAudioSource",
    "FileAudioSource",
    "URLAudioSource",
)

class AudioSource(ABC):
    """Base audio source implementation."""

    @abstractmethod
    def __init__(self) -> None:
        error: str = "AudioSource should only be subclassed"
        raise NotImplementedError(error)

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        error: str = "AudioSource eq cannot be resolved as it should be subclassed"
        raise NotImplementedError(error)
    
    @abstractmethod
    def __hash__(self) -> int:
        error: str = "AudioSource hash cannot be resolved as it should be subclassed"
        raise NotImplementedError(error)

    def __repr__(self) -> str:
        args: list[str] = []
        for key, value in self.__dict__.items():
            args.append(f"{key.lstrip('_')}={value}")

        return f"{self.__class__.__name__}({', '.join(args)})"

class BufferAudioSource(AudioSource):
    """Buffer audio source implementation."""

    __slots__ = ("_buffer", "name", "_volume",)

    def __init__(self, buffer: bytearray | bytes | memoryview, *, name: str | None = None, volume: float | str | None = None) -> None:
        """
        Create a buffered audio source.
        
        Parameters
        ----------
        buffer : bytearray | bytes | memoryview
            The audio data as a buffer.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        """

        self._buffer: bytearray | bytes | memoryview = buffer
        self._volume: float | str | None = volume

        self.name: str | None = name
        """The assigned name of this source for display purposes, if provided."""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BufferAudioSource): return False
        return self._buffer == other._buffer
    
    def __hash__(self) -> int:
        return hash(self._buffer)
    
    @property
    def buffer(self) -> bytearray | bytes | memoryview:
        """The audio data as a buffer."""
        return self._buffer

    @property
    def volume(self) -> float | str | None:
        """If provided, the overriding volume for this source."""
        return self._volume

class FileAudioSource(AudioSource):
    """File audio source implementation."""

    __slots__ = ("_filepath", "name", "_volume",)

    def __init__(self, filepath: str, *, name: str | None = None, volume: float | str | None = None) -> None:
        """
        Create a file audio source.
        
        Parameters
        ----------
        filepath : str
            The path, absolute or relative, to the audio file.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        """

        if not os.path.exists(filepath):
            error: str = f"Provided filepath does not exist: {filepath}"
            raise FileNotFoundError(error)
        
        self._filepath: str = filepath
        self._volume: float | str | None = volume

        self.name: str | None = name
        """The assigned name of this source for display purposes, if provided."""
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileAudioSource): return False
        return self._filepath == other._filepath

    def __hash__(self) -> int:
        return hash(self._filepath)

    @property
    def filepath(self) -> str:
        """The path, absolute or relative, to the audio file."""
        return self._filepath
    
    @property
    def volume(self) -> float | str | None:
        """If provided, the overriding volume for this source."""
        return self._volume

class URLAudioSource(AudioSource):
    """URL audio source implementation."""

    __slots__ = ("_url", "name", "_volume",)

    def __init__(self, url: str, *, name: str | None = None, volume: float | str | None = None) -> None:
        """
        Create a URL-based audio source.
        
        Parameters
        ----------
        url : str
            The direct URL to an audio source.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).
        """
        
        self._url: str = url
        self._volume: float | str | None = volume

        self.name: str | None = name
        """The assigned name of this source for display purposes, if provided."""
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, URLAudioSource): return False
        return self._url == other._url

    def __hash__(self) -> int:
        return hash(self._url)

    @property
    def url(self) -> str:
        """The direct URL to an audio source."""
        return self._url
    
    @property
    def volume(self) -> float | str | None:
        """If provided, the overriding volume for this source."""
        return self._volume
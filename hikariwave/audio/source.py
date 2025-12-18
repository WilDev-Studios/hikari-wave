from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = (
    "AudioSource",
    "FileAudioSource",
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

class FileAudioSource(AudioSource):
    """File audio source implementation."""

    def __init__(self, filepath: str, *, name: str | None = None) -> None:
        """
        Create a file audio source.
        
        Parameters
        ----------
        filepath : str
            The path, absolute or relative, to the audio file.
        name : str | None
            If provided, an internal name used for display purposes - Default `None`.
        """
        
        self._filepath: str = filepath

        self.name: str | None = name
        """The assigned name of this source for display purposes, if provided."""
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileAudioSource): return False
        return self._filepath == other._filepath

    def __hash__(self) -> int:
        return hash(self.filepath)

    @property
    def filepath(self) -> str:
        """The path, absolute or relative, to the audio file."""
        return self._filepath
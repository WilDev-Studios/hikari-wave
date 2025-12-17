from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

import aiofiles

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

    @abstractmethod
    async def read(self) -> bytes:
        """
        Read the entire contents of this source.
        
        Returns
        -------
        bytes
            The contents of this source.
        """

        error: str = "AudioSource.read should only be called in a subclass"
        raise NotImplementedError(error)

    @abstractmethod
    async def stream(self, size: int) -> AsyncGenerator[bytes, Any]:
        """
        Stream the contents of this source in chunks.
        
        Parameters
        ----------
        size : int
            The amount of bytes to stream in each chunk.
        
        Yields
        ------
        bytes
            Each chunk of audio from this source.
        """

        error: str = "AudioSource.stream should only be called in a subclass"
        raise NotImplementedError(error)

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
        return self.filepath == other.filepath

    def __hash__(self) -> int:
        return hash(self.filepath)

    @property
    def filepath(self) -> str:
        """The path, absolute or relative, to the audio file."""
        return self._filepath

    async def read(self) -> bytes:
        async with aiofiles.open(self._filepath, "rb") as file:
            return await file.read()
    
    async def stream(self, size: int) -> AsyncGenerator[bytes, Any]:
        async with aiofiles.open(self._filepath, "rb") as file:
            while True:
                chunk: bytes = await file.read(size)

                if not chunk or len(chunk) != size:
                    return

                yield chunk
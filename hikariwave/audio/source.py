from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

import aiofiles

class AudioSource(ABC):
    """Base audio source implementation."""

    @abstractmethod
    async def read(self) -> bytes:
        """
        Read the entire contents of this source.
        
        Returns
        -------
        bytes
            The contents of this source.
        """

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

class FileAudioSource(AudioSource):
    """File audio source implementation."""

    def __init__(self, filepath: str) -> None:
        """
        Create a file audio source.
        
        Parameters
        ----------
        filepath : str
            The path, relative or absolute, to the audio file.
        """
        
        self.filepath: str = filepath

    async def read(self) -> bytes:
        async with aiofiles.open(self.filepath, "rb") as file:
            return await file.read()
    
    async def stream(self, size: int) -> AsyncGenerator[bytes, Any]:
        async with aiofiles.open(self.filepath, "rb") as file:
            while True:
                chunk: bytes = await file.read(size)

                if not chunk or len(chunk) != size:
                    return

                yield chunk
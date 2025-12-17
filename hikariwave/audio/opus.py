from __future__ import annotations

from hikariwave.constants import Audio

import os
import sys

script_dir: str = os.path.dirname(os.path.abspath(__file__))
bin_dir: str = os.path.join(script_dir, "bin")

if sys.platform == "win32":
    os.environ["PATH"] = f"{bin_dir};{os.environ['PATH']}"
    os.add_dll_directory(bin_dir)

import opuslib

class OpusEncoder:
    """Responsible for encoding PCM audio to Opus."""

    def __init__(self) -> None:
        """
        Create an Opus encoder.
        """
        
        self._encoder: opuslib.Encoder = None
    
    async def encode(self, pcm: bytes) -> bytes:
        """
        Encode PCM into Opus audio.
        
        Parameters
        ----------
        pcm : bytes
            The PCM audio to encode.
        
        Returns
        -------
        bytes | None
            The Opus-encoded audio, if any.
        """
        
        if not self._encoder:
            return
        
        pcm = pcm[:Audio.FRAME_SIZE].ljust(
            Audio.FRAME_SIZE, b"\0",
        )
        return self._encoder.encode(pcm, Audio.SAMPLES_PER_FRAME)

    async def start(self) -> None:
        """
        Start the internal encoder to encode PCM.
        """
        
        if self._encoder: return

        self.frame_samples = (
            Audio.FRAME_SIZE //
            (Audio.CHANNELS * 2)
        )

        self._encoder = opuslib.Encoder(
            Audio.SAMPLING_RATE,
            Audio.CHANNELS,
            opuslib.APPLICATION_AUDIO,
        )
    
    async def stop(self) -> None:
        """
        Stop the internal encoder.
        """
        
        self._encoder = None
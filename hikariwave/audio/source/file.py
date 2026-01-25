from __future__ import annotations

from hikariwave.audio.source.base import (
    AudioSource,
    validate_content,
    validate_duration,
    validate_name,
)
from hikariwave.config import (
    validate_bitrate,
    validate_channels,
    validate_volume,
)

import os

__all__ = ("FileAudioSource",)

class FileAudioSource(AudioSource):
    """
    File audio source implementation.

    Warning
    -------
    This source is intended primarily for testing, development, and simple use cases.
    For production, URL-based or other sources are recommended.
    Some fields and properties cannot be reliably retrieved without excessive dependencies.
    """

    __slots__ = (
        "_content",
        "_duration",
        "_bitrate",
        "_channels",
        "_name",
        "_volume",
    )

    def __init__(
        self,
        filepath: str,
        duration: float | None = None,
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
        duration : float | None
            If provided, the duration of this source - Required if using player timestamp properties/fields.
        bitrate : str | None
            If provided, the bitrate in which to play this source back at.
        channels : int | None
            If provided, the amount of channels this source plays with.
        name : str | None
            If provided, an internal name used for display purposes.
        volume : float | str | None
            If provided, overrides the player's set/default volume. Can be scaled (`0.5`, `1.0`, `2.0`, etc.) or dB-based (`-3dB`, etc.).

        Warning
        -------
        This source is intended primarily for testing, development, and simple use cases.
        For production, URL-based or other sources are recommended.
        Some fields and properties cannot be reliably retrieved without excessive dependencies.

        Raises
        ------
        TypeError
            - If `filepath` is not `str`.
            - If `duration` is provided and not `float`.
            - If `bitrate` is provided and not `str`.
            - If `channels` is provided and not `int`.
            - If `name` is provided and not `str`.
            - If `volume` is provided and not `float` or `str`.
        ValueError
            - If `filepath` is empty or is not found as a file on the system.
            - If `duration` is provided and is not greater than `0`.
            - If `bitrate` is provided, and is not between `6k` and `510k`.
            - If `channels` is provided and not `1` or `2`.
            - If `name` is provided and is empty.
            - If `volume` is provided and is either a `float` and is not positive or a `str` and does not end with `dB`, contain a number, or (if provided) doesn't begin with `-` or `+`.
        """

        self._content: str = validate_content(filepath, "filepath", (str,))
        self._duration: float | None = validate_duration(duration) if duration is not None else None

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

        if not os.path.isfile(self._content):
            error: str = f"No file exists at this path: {self._content}"
            raise FileNotFoundError(error)

    @property
    def filepath(self) -> str:
        """The filepath to the audio file"""
        return self._content

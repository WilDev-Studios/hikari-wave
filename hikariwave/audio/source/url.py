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

__all__ = ("URLAudioSource",)

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

        self._content: str = validate_content(url, "url", (str,))

        self._bitrate: str | None = validate_bitrate(bitrate) if bitrate is not None else None
        self._channels: int | None = validate_channels(channels) if channels is not None else None
        self._name: str | None = validate_name(name) if name is not None else None
        self._volume: float | str | None = validate_volume(volume) if volume is not None else None

    @property
    def url(self) -> str:
        """The URL to the audio source."""
        return self._content
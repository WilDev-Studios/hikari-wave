from __future__ import annotations

from enum import auto, IntEnum

__all__ = (
    "AudioBeginOrigin",
    "VoiceWarningType",
)

class AudioBeginOrigin(IntEnum):
    """The origin of an `AudioBeginEvent`."""

    HISTORY = auto()
    """Audio playing from player history."""
    PLAY = auto()
    """Audio playing from a direct call, i.e. `play()`."""
    QUEUE = auto()
    """Audio playing from player queue."""

class VoiceWarningType(IntEnum):
    """A type of voice warning."""

    JITTER           = auto()
    """Maximum jitter has been exceeded."""
    PACKET_LOSS      = auto()
    """Maximum packet loss has been exceeded."""
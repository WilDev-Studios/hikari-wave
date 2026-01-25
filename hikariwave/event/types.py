from __future__ import annotations

from enum import IntEnum

__all__ = (
    "AudioBeginOrigin",
    "VoiceWarningType",
)

class AudioBeginOrigin(IntEnum):
    """The origin of an `AudioBeginEvent`."""

    HISTORY = 0
    """Audio playing from player history."""
    PLAY    = 1
    """Audio playing from a direct call, i.e. `play()`."""
    QUEUE   = 2
    """Audio playing from player queue."""

class VoiceWarningType(IntEnum):
    """A type of voice warning."""

    JITTER      = 0
    """Maximum jitter has been exceeded."""
    PACKET_LOSS = 1
    """Maximum packet loss has been exceeded."""

from __future__ import annotations

from enum import auto, IntEnum

__all__ = (
    "AudioBeginOrigin",
    "VoiceWarningType",
    "WaveEventType",
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

class WaveEventType(IntEnum):
    """A type of supplemental event."""

    ALL                   = auto()
    """Base event listener - Receives all events."""
    AUDIO_BEGIN           = auto()
    """When audio begins playing."""
    AUDIO_END             = auto()
    """When audio stops playing."""
    AUDIO_SECOND          = auto()
    """When audio advances by a second."""
    BOT_JOIN_VOICE        = auto()
    """When the bot joins a channel."""
    BOT_LEAVE_VOICE       = auto()
    """When the bot leaves a channel."""
    MEMBER_DEAF           = auto()
    """When a member deafens/undeafens."""
    MEMBER_JOIN_VOICE     = auto()
    """When a member joins a channel."""
    MEMBER_LEAVE_VOICE    = auto()
    """When a member leaves a channel."""
    MEMBER_MOVE_VOICE     = auto()
    """When a member moves channels."""
    MEMBER_MUTE           = auto()
    """When a member mutes/unmutes."""
    MEMBER_START_SPEAKING = auto()
    """When a member starts speaking."""
    MEMBER_STOP_SPEAKING  = auto()
    """When a member stops speaking."""
    VOICE_RECONNECT       = auto()
    """When a voice connection has to reconnect."""
    VOICE_WARNING         = auto()
    """When a voice connection issues a warning."""
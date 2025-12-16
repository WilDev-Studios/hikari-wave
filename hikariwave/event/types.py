from __future__ import annotations

from enum import auto, IntEnum
from typing import Final, Sequence

__all__: Final[Sequence[str]] = (
    "VoiceWarningType",
    "WaveEventType",
)

class VoiceWarningType(IntEnum):
    """A type of voice warning."""

    LATENCY          = auto()
    """Voice server connection has a high latency."""
    UNHANDLED_OPCODE = auto()
    """Voice gateway received an unhandled operation code."""

class WaveEventType(IntEnum):
    """A type of supplemental event."""

    ALL                   = auto()
    """Base event listener - Receives all events."""
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
    VOICE_ACTIVE          = auto()
    """When a channel has member(s) speaking."""
    VOICE_EMPTY           = auto()
    """When a channel becomes empty."""
    VOICE_INACTIVE        = auto()
    """When a channel no longer has member(s) speaking."""
    VOICE_POPULATED       = auto()
    """When a channel becomes populated."""
    VOICE_RECONNECT       = auto()
    """When a voice connection has to reconnect."""
    VOICE_WARNING         = auto()
    """When a voice connection issues a warning."""
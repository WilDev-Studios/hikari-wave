from __future__ import annotations

from dataclasses import dataclass
from hikariwave.event.events.base import WaveEvent

import hikari

__all__ = (
    "MemberEvent",
    "MemberDeafEvent",
    "MemberJoinEvent",
    "MemberLeaveEvent",
    "MemberMoveEvent",
    "MemberMuteEvent",
    "MemberSpeechEvent",
    "MemberStartSpeakingEvent",
    "MemberStopSpeakingEvent",
)

@dataclass(frozen=True, init=False, slots=True)
class MemberEvent(WaveEvent):
    """Base member event implementation."""

    member: hikari.Member
    """The member that this event references."""

@dataclass(frozen=True, init=False, slots=True)
class MemberDeafEvent(MemberEvent):
    """Dispatched when a member in a voice channel deafens/undeafens (themself/server)."""

    is_deaf: bool
    """If the member is deafened."""

@dataclass(frozen=True, init=False, slots=True)
class MemberJoinEvent(MemberEvent):
    """Dispatched when a member joins a voice channel."""

@dataclass(frozen=True, init=False, slots=True)
class MemberLeaveEvent(MemberEvent):
    """Dispatched when a member leaves a voice channel."""

@dataclass(frozen=True, init=False, slots=True)
class MemberMoveEvent(MemberEvent):
    """Dispatched when a member moves voice channels."""

    old_channel_id: hikari.Snowflake
    """The ID of the channel that was left."""

@dataclass(frozen=True, init=False, slots=True)
class MemberMuteEvent(MemberEvent):
    """Dispatched when a member in a voice channel mutes/unmutes (themself/server)."""

    is_mute: bool
    """If the member is muted."""

@dataclass(frozen=True, init=False, slots=True)
class MemberSpeechEvent(MemberEvent):
    """Dispatched when a member in a voice channel finishes speaking and you wish to handle their voice packets."""

    audio: list[bytes]
    """The Opus audio emitted from this member."""

@dataclass(frozen=True, init=False, slots=True)
class MemberStartSpeakingEvent(MemberEvent):
    """Dispatched when a member in a voice channel begins speaking."""

@dataclass(frozen=True, init=False, slots=True)
class MemberStopSpeakingEvent(MemberEvent):
    """Dispatched when a member in a voice channel stops speaking."""
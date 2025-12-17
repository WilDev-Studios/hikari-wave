from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from hikariwave.audio.source import AudioSource
from hikariwave.event.types import VoiceWarningType

import hikari

__all__ = (
    "WaveEvent",
    "AudioBeginEvent",
    "AudioEndEvent",
    "BotJoinVoiceEvent",
    "BotLeaveVoiceEvent",
    "MemberDeafEvent",
    "MemberJoinVoiceEvent",
    "MemberLeaveVoiceEvent",
    "MemberMoveVoiceEvent",
    "MemberMuteEvent",
    "MemberStartSpeakingEvent",
    "MemberStopSpeakingEvent",
    "VoiceActiveEvent",
    "VoiceEmptyEvent",
    "VoiceInactiveEvent",
    "VoicePopulatedEvent",
    "VoiceReconnectEvent",
    "VoiceWarningEvent",
)

class WaveEvent(hikari.Event, ABC):
    """Base event listener for all `hikari-wave` supplemental events, for convenience."""

    def __init__(self, *_) -> None:
        error: str = "Events cannot be instantiated directly"
        raise RuntimeError(error)

    @property
    def app(self) -> hikari.RESTAware: return super().app

    @classmethod
    @abstractmethod
    def _create(cls) -> WaveEvent:...

@dataclass(frozen=True, slots=True)
class AudioBeginEvent(WaveEvent):
    """Dispatched when audio begins playing in a voice channel."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""
    audio: AudioSource
    """The audio that is playing."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        audio: AudioSource,
    ) -> AudioBeginEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "audio", audio)
        return self

@dataclass(frozen=True, slots=True)
class AudioEndEvent(WaveEvent):
    """Dispatched when audio stops playing in a voice channel."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""
    audio: AudioSource
    """The audio that is no longer playing."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        audio: AudioSource,
    ) -> AudioBeginEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "audio", audio)
        return self

@dataclass(frozen=True, slots=True)
class BotJoinVoiceEvent(WaveEvent):
    """Dispatched when the current bot joins a voice channel."""

    bot: hikari.GatewayBot
    """The current bot that joined the channel, for convenience."""
    channel_id: hikari.Snowflake
    """The ID of the channel that was joined."""
    guild_id: hikari.Snowflake
    """The ID of the guild that the channel is in."""
    is_deaf: bool
    """If the current bot is deafened."""
    is_mute: bool
    """If the current bot is muted."""

    @classmethod
    def _create(
        cls,
        bot: hikari.GatewayBot,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        deafened: bool,
        muted: bool,
    ) -> BotJoinVoiceEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "bot", bot)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "is_deaf", deafened)
        object.__setattr__(self, "is_mute", muted)
        return self

@dataclass(frozen=True, slots=True)
class BotLeaveVoiceEvent(WaveEvent):
    """Dispatched when the current bot leaves a voice channel."""

    bot: hikari.GatewayBot
    """The current bot that left the channel, for convenience."""
    channel_id: hikari.Snowflake
    """The ID of the channel that was left."""
    guild_id: hikari.Snowflake
    """The ID of the guild that the channel is in."""

    @classmethod
    def _create(
        cls,
        bot: hikari.GatewayBot,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> BotLeaveVoiceEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "bot", bot)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class MemberDeafEvent(WaveEvent):
    """Dispatched when a member in a voice channel deafens/undeafens (themself/server), excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel the member is in."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that deafened/undeafened."""
    is_deaf: bool
    """If the member is deafened."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
        deaf: bool,
    ) -> MemberDeafEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        object.__setattr__(self, "is_deaf", deaf)
        return self

@dataclass(frozen=True, slots=True)
class MemberJoinVoiceEvent(WaveEvent):
    """Dispatched when a member joins a voice channel, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel that was joined."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that joined the channel."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
    ) -> MemberJoinVoiceEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        return self

@dataclass(frozen=True, slots=True)
class MemberLeaveVoiceEvent(WaveEvent):
    """Dispatched when a member leaves a voice channel, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel that was left."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that left the channel."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
    ) -> MemberLeaveVoiceEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        return self

@dataclass(frozen=True, slots=True)
class MemberMoveVoiceEvent(WaveEvent):
    """Dispatched when a member moves voice channels, excluding the current bot."""

    guild_id: hikari.Snowflake
    """The ID of the guild that the channels are in."""
    member: hikari.Member
    """The member that moved channels."""
    new_channel_id: hikari.Snowflake
    """The ID of the channel that was joined."""
    old_channel_id: hikari.Snowflake
    """The ID of the channel that was left."""

    @classmethod
    def _create(
        cls,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
        new_channel_id: hikari.Snowflake,
        old_channel_id: hikari.Snowflake,
    ) -> MemberMoveVoiceEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        object.__setattr__(self, "new_channel_id", new_channel_id)
        object.__setattr__(self, "old_channel_id", old_channel_id)
        return self

@dataclass(frozen=True, slots=True)
class MemberMuteEvent(WaveEvent):
    """Dispatched when a member in a voice channel mutes/unmutes (themself/server), excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel the member is in."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that muted/unmuted."""
    is_mute: bool
    """If the member is muted."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
        mute: bool,
    ) -> MemberMuteEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        object.__setattr__(self, "is_mute", mute)
        return self

@dataclass(frozen=True, slots=True)
class MemberStartSpeakingEvent(WaveEvent):
    """Dispatched when a member in a voice channel begins speaking, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel the member is in."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that is speaking."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
    ) -> MemberStartSpeakingEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        return self

@dataclass(frozen=True, slots=True)
class MemberStopSpeakingEvent(WaveEvent):
    """Dispatched when a member in a voice channel stops speaking, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel the member is in."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel/member is in."""
    member: hikari.Member
    """The member that is no longer speaking."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        member: hikari.Member,
    ) -> MemberStopSpeakingEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "member", member)
        return self

@dataclass(frozen=True, slots=True)
class VoiceActiveEvent(WaveEvent):
    """Dispatched when a voice channel becomes active (members speaking), excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel that is active."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> VoiceInactiveEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class VoiceEmptyEvent(WaveEvent):
    """Dispatched when there are no other users in a voice channel, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> VoiceEmptyEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class VoiceInactiveEvent(WaveEvent):
    """Dispatched when a voice channel becomes inactive (no members speaking), excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel that is inactive."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> VoiceInactiveEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class VoicePopulatedEvent(WaveEvent):
    """Dispatched when a voice channel gains its first member, excluding the current bot."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> VoicePopulatedEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class VoiceReconnectEvent(WaveEvent):
    """Dispatched when a voice connection reconnects or resumes."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
    ) -> VoicePopulatedEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        return self

@dataclass(frozen=True, slots=True)
class VoiceWarningEvent(WaveEvent):
    """Dispatched when non-fatal voice issues occur (packet loss, jitter, latency)."""

    channel_id: hikari.Snowflake
    """The ID of the channel this warning was issued for."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""
    type: VoiceWarningType
    """The type of warning that was issued."""
    details: str | int | None
    """Any contextual information that may be provided."""

    @classmethod
    def _create(
        cls,
        channel_id: hikari.Snowflake,
        guild_id: hikari.Snowflake,
        type: VoiceWarningType,
        details: str | int | None = None,
    ) -> VoiceWarningEvent:
        self = object.__new__(cls)
        object.__setattr__(self, "channel_id", channel_id)
        object.__setattr__(self, "guild_id", guild_id)
        object.__setattr__(self, "type", type)
        object.__setattr__(self, "details", details)
        return self
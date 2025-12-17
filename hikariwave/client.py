from __future__ import annotations

from dataclasses import dataclass
from hikariwave.audio.ffmpeg import FFmpeg
from hikariwave.connection import VoiceConnection
from hikariwave.error import GatewayError
from hikariwave.event.factory import EventFactory
from hikariwave.event.types import WaveEventType
from typing import Final, Sequence, TypeAlias

import asyncio
import hikari
import logging

__all__: Final[Sequence[str]] = ("VoiceClient",)

logger: logging.Logger = logging.getLogger("hikari-wave.client")

ChannelID: TypeAlias = hikari.Snowflakeish
GuildID: TypeAlias = hikari.Snowflakeish
MemberID: TypeAlias = hikari.Snowflakeish

@dataclass(slots=True)
class VoiceChannelMeta:
    """Metadata container for a voice channel."""

    active: set[hikari.Snowflake]
    """A set of all actively speaking users in this channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild this channel is in."""
    id: hikari.Snowflake
    """The ID of this channel."""
    population: int
    """How many users are in this channel."""

@dataclass(slots=True)
class VoiceMemberMeta:
    """Metadata container for a member."""

    channel_id: hikari.Snowflake
    """The ID of the channel this member is in."""
    is_mute: bool
    """If the member is muted."""
    is_deaf: bool
    """If the member is deafened."""

class VoiceClient:
    """Voice system implementation for `hikari`-based Discord bots."""

    def __init__(
        self,
        bot: hikari.GatewayBot,
    ) -> None:
        """
        Create a new voice client.
        
        Parameters
        ----------
        bot : hikari.GatewayBot
            The `hikari`-based Discord bot to link this voice system with.
        """
        
        self._bot: hikari.GatewayBot = bot
        self._bot.subscribe(hikari.VoiceStateUpdateEvent, self._disconnected)
        self._bot.subscribe(hikari.VoiceStateUpdateEvent, self._voice_state_update)

        self._connections: dict[GuildID, VoiceConnection] = {}
        self._connections_reference: dict[ChannelID, GuildID] = {}

        self._members: dict[MemberID, VoiceMemberMeta] = {}
        self._channels: dict[ChannelID, VoiceChannelMeta] = {}
        self._views: dict[MemberID, hikari.Member] = {}
        self._ssrcs: dict[MemberID, int] = {}
        self._ssrcs_reference: dict[int, MemberID] = {}

        self._event_factory: EventFactory = EventFactory(self._bot)

        self._ffmpeg: FFmpeg = FFmpeg()
    
    async def _disconnect(self, guild_id: hikari.Snowflakeish) -> None:
        connection: VoiceConnection = self._connections.pop(guild_id)

        logger.info(f"Disconnecting from voice: Guild={guild_id}, Channel={connection._channel_id}")

        del self._connections_reference[connection._channel_id]
        await connection._disconnect()

        self._event_factory.emit(
            WaveEventType.BOT_LEAVE_VOICE,
            self._bot,
            connection._channel_id,
            guild_id,
        )

        if len(self._connections) == 0:
            await self._ffmpeg.stop()

    async def _disconnected(self, event: hikari.VoiceStateUpdateEvent) -> None:
        if event.state.user_id != self._bot.get_me().id:
            return
        
        if event.guild_id not in self._connections:
            return
        
        await self._disconnect(event.guild_id)

    async def _voice_state_update(self, event: hikari.VoiceStateUpdateEvent) -> None:
        state: hikari.VoiceState = event.state

        if state.user_id == self._bot.get_me().id: return
        if not state.member: return

        channel: hikari.Snowflake = state.channel_id
        guild: hikari.Snowflake = state.guild_id
        member: hikari.Member = state.member

        in_voice: bool = member.id in self._members

        if channel and not in_voice:
            self._members[member.id] = VoiceMemberMeta(channel, state.is_guild_muted or state.is_self_muted, state.is_guild_deafened or state.is_self_deafened)
            self._views[member.id] = member

            if channel not in self._channels:
                self._channels[channel] = VoiceChannelMeta(set(), guild, channel, 0)
                self._event_factory.emit(
                    WaveEventType.VOICE_POPULATED,
                    channel,
                    guild,
                )
            
            self._channels[channel].population += 1
            self._event_factory.emit(
                WaveEventType.MEMBER_JOIN_VOICE,
                channel,
                guild,
                member,
            )
            return
        
        if not channel and in_voice:
            channel = self._members[member.id].channel_id
            cmeta: VoiceChannelMeta = self._channels[channel]
            cmeta.population -= 1

            if cmeta.population < 1:
                del self._channels[channel]
                self._event_factory.emit(
                    WaveEventType.VOICE_EMPTY,
                    channel,
                    guild,
                )

            del self._members[member.id]
            del self._views[member.id]

            if member.id in self._ssrcs:
                ssrc: int = self._ssrcs.pop(member.id)
                del self._ssrcs_reference[ssrc]
            
            return self._event_factory.emit(
                WaveEventType.MEMBER_LEAVE_VOICE,
                channel,
                guild,
                member,
            )
        
        if channel and in_voice and self._members[member.id].channel_id != channel:
            meta: VoiceMemberMeta = self._members[member.id]
            self._event_factory.emit(
                WaveEventType.MEMBER_MOVE_VOICE,
                guild,
                member,
                channel,
                meta.channel_id,
            )
            meta.channel_id = channel

            self._views[member.id] = member
            return

        if channel:
            meta: VoiceMemberMeta = self._members[member.id]
            deaf: bool = event.state.is_self_deafened or event.state.is_guild_deafened
            mute: bool = event.state.is_self_muted or event.state.is_guild_muted

            if deaf != meta.is_deaf:
                meta.is_deaf = deaf
                self._event_factory.emit(
                    WaveEventType.MEMBER_DEAF,
                    channel,
                    guild,
                    member,
                    deaf,
                )
            
            if mute != meta.is_mute:
                meta.is_mute = mute
                self._event_factory.emit(
                    WaveEventType.MEMBER_MUTE,
                    channel,
                    guild,
                    member,
                    mute,
                )
            
            self._views[member.id] = member

    @property
    def bot(self) -> hikari.GatewayBot:
        """The controlling OAuth2 bot."""
        return self._bot

    async def connect(
        self,
        guild_id: hikari.Snowflakeish,
        channel_id: hikari.Snowflakeish,
        *,
        mute: bool = False,
        deaf: bool = True,
    ) -> VoiceConnection:
        """
        Connect to a voice channel.
        
        Parameters
        ----------
        guild_id : hikari.Snowflakeish
            The ID of the guild that the channel is in.
        channel_id : hikari.Snowflakeish
            The ID of the channel to connect to.
        mute : bool 
            If the bot should be muted upon joining the channel - Default `False`.
        deaf : bool
            If the bot should be deafened upon joining the channel - Default `True`.
        
        Returns
        -------
        VoiceConnection
            The active connection to the voice channel, once fully connected.
        
        Raises
        ------
        asyncio.TimeoutError
            If Discord doesn't send a corresponding voice server/state update.
        """

        logger.info(f"Connecting to voice: Guild={guild_id}, Channel={channel_id}, Mute={mute}, Deaf={deaf}")

        await self._bot.update_voice_state(guild_id, channel_id, self_mute=mute, self_deaf=deaf)

        try:
            server_update, state_update = await asyncio.gather(
                self._bot.wait_for(
                    hikari.VoiceServerUpdateEvent, 3.0,
                    lambda e: e.guild_id == guild_id
                ),
                self._bot.wait_for(
                    hikari.VoiceStateUpdateEvent, 3.0,
                    lambda e: e.guild_id == guild_id and e.state.channel_id == channel_id and e.state.user_id == self._bot.get_me().id
                )
            )
        except asyncio.TimeoutError:
            error: str = "Voice server/state update timed out"
            raise GatewayError(error)

        guild: hikari.Guild = await self._bot.rest.fetch_guild(guild_id)
        population: int = 0
        for state in guild.get_voice_states().values():
            self._members[state.member.id] = VoiceMemberMeta(channel_id, state.is_guild_muted or state.is_self_muted, state.is_guild_deafened or state.is_self_deafened)
            self._views[state.member.id] = state.member
            
            population += 1
        self._channels[channel_id] = VoiceChannelMeta(set(), guild_id, channel_id, population)

        connection: VoiceConnection = VoiceConnection(
            self,
            guild_id,
            channel_id,
            server_update.endpoint,
            state_update.state.session_id,
            server_update.token,
        )
        await connection._connect()
        self._connections[guild_id] = connection
        self._connections_reference[channel_id] = guild_id

        self._event_factory.emit(
            WaveEventType.BOT_JOIN_VOICE,
            self._bot,
            channel_id,
            guild_id,
            deaf,
            mute,
        )

        return connection
    
    @property
    def connections(self) -> dict[hikari.Snowflake, VoiceConnection]:
        """A mapping of all voice connections."""
        return dict(self._connections)

    async def disconnect(
        self,
        *,
        guild_id: hikari.Snowflakeish | None = None,
        channel_id: hikari.Snowflakeish | None = None,
    ) -> None:
        """
        Disconnect from a voice channel.
        
        Parameters
        ----------
        guild_id : hikari.Snowflakeish | None
            The ID of the guild that the channel to disconnect from is in - Default `None`.
        channel_id : hikari.Snowflakeish | None
            The ID of the channel to disconnect from - Default `None`.
        
        Note
        ----
        At least one of `guild_id` or `channel_id` must be provided.

        Raises
        ------
        ValueError
            If neither of `guild_id` or `channel_id` are provided.
        """
        
        if not guild_id and not channel_id:
            error: str = "At least guild_id or channel_id must be defined"
            raise ValueError(error)
        
        if channel_id:
            guild_id = self._connections_reference[channel_id]

        await self._bot.update_voice_state(guild_id, None)
        await self._disconnect(guild_id)
    
    def get_connection(
        self,
        *,
        guild_id: hikari.Snowflakeish | None = None,
        channel_id: hikari.Snowflakeish | None = None,
    ) -> VoiceConnection | None:
        """
        Get an active voice connection.
        
        Parameters
        ----------
        guild_id : hikari.Snowflakeish | None
            The ID of the guild that the connection is handling - Default `None`.
        channel_id : hikari.Snowflakeish | None
            The ID of the channel that the connection is handling - Default `None`.
        
        Note
        ----
        At least one of `guild_id` or `channel_id` must be provided.
        
        Returns
        -------
        VoiceConnection | None
            The active voice connection at the guild/channel, if present.

        Raises
        ------
        ValueError
            If neither of `guild_id` or `channel_id` are provided.
        """

        if not guild_id and not channel_id:
            error: str = "At least guild_id or channel_id must be defined"
            raise ValueError(error)
        
        if channel_id:
            guild_id = self._connections_reference[channel_id]
        
        try:
            return self._connections[guild_id]
        except KeyError:
            return
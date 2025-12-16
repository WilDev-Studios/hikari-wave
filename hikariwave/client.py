from __future__ import annotations

from dataclasses import dataclass
from hikariwave.audio.ffmpeg import FFmpegDecoder
from hikariwave.audio.opus import OpusEncoder
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
        
        self.bot: hikari.GatewayBot = bot
        self.bot.subscribe(hikari.VoiceStateUpdateEvent, self._disconnected)
        self.bot.subscribe(hikari.VoiceStateUpdateEvent, self._voice_state_update)

        self.connections: dict[GuildID, VoiceConnection] = {}
        self.connections_reference: dict[ChannelID, GuildID] = {}

        self.members: dict[MemberID, VoiceMemberMeta] = {}
        self.channels: dict[ChannelID, VoiceChannelMeta] = {}
        self.views: dict[MemberID, hikari.Member] = {}
        self.ssrcs: dict[MemberID, int] = {}
        self.ssrcs_reference: dict[int, MemberID] = {}

        self.event_factory: EventFactory = EventFactory(self.bot)

        self.ffmpeg: FFmpegDecoder = FFmpegDecoder()
        self.opus: OpusEncoder = OpusEncoder()
    
    async def _disconnect(self, guild_id: hikari.Snowflakeish) -> None:
        connection: VoiceConnection = self.connections.pop(guild_id)

        logger.info(f"Disconnecting from voice: Guild={guild_id}, Channel={connection.channel_id}")

        del self.connections_reference[connection.channel_id]
        await connection._disconnect()

        self.event_factory.emit(
            WaveEventType.BOT_LEAVE_VOICE,
            self.bot,
            connection.channel_id,
            guild_id,
        )

        if len(self.connections) == 0:
            await self.opus.stop()
            await self.ffmpeg.stop()

    async def _disconnected(self, event: hikari.VoiceStateUpdateEvent) -> None:
        if event.state.user_id != self.bot.get_me().id:
            return
        
        if event.guild_id not in self.connections:
            return
        
        await self._disconnect(event.guild_id)

    async def _voice_state_update(self, event: hikari.VoiceStateUpdateEvent) -> None:
        state: hikari.VoiceState = event.state

        if state.user_id == self.bot.get_me().id: return
        if not state.member: return

        channel: hikari.Snowflake = state.channel_id
        guild: hikari.Snowflake = state.guild_id
        member: hikari.Member = state.member

        in_voice: bool = member.id in self.members

        if channel and not in_voice:
            self.members[member.id] = VoiceMemberMeta(channel, state.is_guild_muted or state.is_self_muted, state.is_guild_deafened or state.is_self_deafened)
            self.views[member.id] = member

            if channel not in self.channels:
                self.channels[channel] = VoiceChannelMeta(set(), guild, channel, 0)
                self.event_factory.emit(
                    WaveEventType.VOICE_POPULATED,
                    channel,
                    guild,
                )
            
            self.channels[channel].population += 1
            self.event_factory.emit(
                WaveEventType.MEMBER_JOIN_VOICE,
                channel,
                guild,
                member,
            )
            return
        
        if not channel and in_voice:
            channel = self.members[member.id].channel_id
            cmeta: VoiceChannelMeta = self.channels[channel]
            cmeta.population -= 1

            if cmeta.population < 1:
                del self.channels[channel]
                self.event_factory.emit(
                    WaveEventType.VOICE_EMPTY,
                    channel,
                    guild,
                )

            del self.members[member.id]
            del self.views[member.id]

            if member.id in self.ssrcs:
                ssrc: int = self.ssrcs.pop(member.id)
                del self.ssrcs_reference[ssrc]
            
            return self.event_factory.emit(
                WaveEventType.MEMBER_LEAVE_VOICE,
                channel,
                guild,
                member,
            )
        
        if channel and in_voice and self.members[member.id].channel_id != channel:
            meta: VoiceMemberMeta = self.members[member.id]
            self.event_factory.emit(
                WaveEventType.MEMBER_MOVE_VOICE,
                guild,
                member,
                channel,
                meta.channel_id,
            )
            meta.channel_id = channel

            self.views[member.id] = member
            return

        if channel:
            meta: VoiceMemberMeta = self.members[member.id]
            deaf: bool = event.state.is_self_deafened or event.state.is_guild_deafened
            mute: bool = event.state.is_self_muted or event.state.is_guild_muted

            if deaf != meta.is_deaf:
                meta.is_deaf = deaf
                self.event_factory.emit(
                    WaveEventType.MEMBER_DEAF,
                    channel,
                    guild,
                    member,
                    deaf,
                )
            
            if mute != meta.is_mute:
                meta.is_mute = mute
                self.event_factory.emit(
                    WaveEventType.MEMBER_MUTE,
                    channel,
                    guild,
                    member,
                    mute,
                )
            
            self.views[member.id] = member

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

        await self.bot.update_voice_state(guild_id, channel_id, self_mute=mute, self_deaf=deaf)

        try:
            server_update, state_update = await asyncio.gather(
                self.bot.wait_for(
                    hikari.VoiceServerUpdateEvent, 3.0,
                    lambda e: e.guild_id == guild_id
                ),
                self.bot.wait_for(
                    hikari.VoiceStateUpdateEvent, 3.0,
                    lambda e: e.guild_id == guild_id and e.state.channel_id == channel_id and e.state.user_id == self.bot.get_me().id
                )
            )
        except asyncio.TimeoutError:
            error: str = "Voice server/state update timed out"
            raise GatewayError(error)

        guild: hikari.Guild = await self.bot.rest.fetch_guild(guild_id)
        population: int = 0
        for state in guild.get_voice_states().values():
            self.members[state.member.id] = VoiceMemberMeta(channel_id, state.is_guild_muted or state.is_self_muted, state.is_guild_deafened or state.is_self_deafened)
            self.views[state.member.id] = state.member
            
            population += 1
        self.channels[channel_id] = VoiceChannelMeta(set(), guild_id, channel_id, population)

        connection: VoiceConnection = VoiceConnection(
            self,
            guild_id,
            channel_id,
            server_update.endpoint,
            state_update.state.session_id,
            server_update.token,
        )
        await connection._connect()
        self.connections[guild_id] = connection
        self.connections_reference[channel_id] = guild_id

        self.event_factory.emit(
            WaveEventType.BOT_JOIN_VOICE,
            self.bot,
            channel_id,
            guild_id,
            deaf,
            mute,
        )

        if len(self.connections) == 1:
            await self.opus.start()

        return connection
    
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
            guild_id = self.connections_reference[channel_id]

        await self.bot.update_voice_state(guild_id, None)
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
            guild_id = self.connections_reference[channel_id]
        
        try:
            return self.connections[guild_id]
        except KeyError:
            return
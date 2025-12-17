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
    members: dict[hikari.Snowflake, hikari.Member]
    """All members inside of this channel."""

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
        self._connectionsr: dict[ChannelID, GuildID] = {}

        self._channels: dict[ChannelID, VoiceChannelMeta] = {}
        self._members: dict[MemberID, ChannelID] = {}
        self._ssrcs: dict[MemberID, int] = {}
        self._ssrcsr: dict[int, MemberID] = {}

        self._states: dict[MemberID, tuple[bool, bool]] = {}

        self._event_factory: EventFactory = EventFactory(self._bot)
        self._ffmpeg: FFmpeg = FFmpeg()
    
    async def _disconnect(self, guild_id: hikari.Snowflakeish) -> None:
        try:
            connection: VoiceConnection = self._connections.pop(guild_id)
        except KeyError:
            return

        logger.info(f"Disconnecting from voice: Guild={guild_id}, Channel={connection._channel_id}")

        del self._connectionsr[connection._channel_id]
        await connection._disconnect()

        cmeta: VoiceChannelMeta = self._channels.pop(connection._channel_id)
        for member_id in cmeta.members.keys():
            del self._members[member_id]
            ssrc: int | None = self._ssrcs.pop(member_id, None)
            if ssrc:
                self._ssrcsr.pop(ssrc, None)

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
        member: hikari.Member = state.member
        if state.user_id == self._bot.get_me().id or not member:
            return
        
        guild_id: hikari.Snowflake = state.guild_id
        old_channel_id: hikari.Snowflake | None = self._members.get(member.id)
        new_channel_id: hikari.Snowflake | None = state.channel_id

        # Member Joined Channel
        if new_channel_id and not old_channel_id:
            member.is_deaf = state.is_guild_deafened or state.is_self_deafened
            member.is_mute = state.is_guild_muted or state.is_self_muted
            self._states[member.id] = (member.is_deaf, member.is_mute)

            if new_channel_id in self._channels:
                cmeta: VoiceChannelMeta = self._channels[new_channel_id]
                cmeta.members[member.id] = member
                self._members[member.id] = new_channel_id

            self._event_factory.emit(
                WaveEventType.MEMBER_JOIN_VOICE,
                new_channel_id,
                guild_id,
                member,
            )
        # Member Moved Channels
        elif new_channel_id and old_channel_id and old_channel_id != new_channel_id:
            if old_channel_id in self._channels:
                cmeta: VoiceChannelMeta = self._channels[old_channel_id]
                del cmeta.members[member.id]
                del self._members[member.id]

                ssrc: int | None = self._ssrcs.pop(member.id, None)
                if ssrc:
                    del self._ssrcsr[ssrc]

            if new_channel_id in self._channels:
                cmeta: VoiceChannelMeta = self._channels[new_channel_id]
                cmeta.members[member.id] = member
                self._members[member.id] = new_channel_id

                ssrc: int | None = self._ssrcs.pop(member.id, None)
                if ssrc:
                    del self._ssrcsr[ssrc]

            self._event_factory.emit(
                WaveEventType.MEMBER_MOVE_VOICE,
                guild_id,
                member,
                new_channel_id,
                old_channel_id,
            )
        # Member Left Channel
        elif not new_channel_id and old_channel_id:
            del self._states[member.id]

            if old_channel_id in self._channels:
                cmeta: VoiceChannelMeta = self._channels[old_channel_id]
                del cmeta.members[member.id]
                del self._members[member.id]

                ssrc: int | None = self._ssrcs.pop(member.id, None)
                if ssrc:
                    del self._ssrcsr[ssrc]

            self._event_factory.emit(
                WaveEventType.MEMBER_LEAVE_VOICE,
                old_channel_id,
                guild_id,
                member,
            )
        # Member Update
        elif new_channel_id and old_channel_id and new_channel_id == old_channel_id:
            member.is_deaf = state.is_guild_deafened or state.is_self_deafened
            member.is_mute = state.is_guild_muted or state.is_self_muted

            old_deaf, old_mute = self._states[member.id]

            if new_channel_id in self._channels:
                cmeta: VoiceChannelMeta = self._channels[new_channel_id]
                cmeta.members[member.id] = member

            if old_deaf != member.is_deaf:
                self._event_factory.emit(
                    WaveEventType.MEMBER_DEAF,
                    new_channel_id,
                    guild_id,
                    member,
                    member.is_deaf,
                )
            
            if old_mute != member.is_mute:
                self._event_factory.emit(
                    WaveEventType.MEMBER_MUTE,
                    new_channel_id,
                    guild_id,
                    member,
                    member.is_mute,
                )
            
            self._states[member.id] = (member.is_deaf, member.is_mute)

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
        members: dict[hikari.Snowflake, hikari.Member] = {}

        for state in guild.get_voice_states().values():
            if state.user_id == self._bot.get_me().id or state.channel_id != channel_id:
                continue

            self._states[state.member.id] = (
                state.is_guild_deafened or state.is_self_deafened,
                state.is_guild_muted or state.is_self_muted,
            )

            members[state.member.id] = state.member
            self._members[state.member.id] = channel_id
        
        self._channels[channel_id] = VoiceChannelMeta(set(), guild_id, channel_id, members)

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
        self._connectionsr[channel_id] = guild_id

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
            guild_id = self._connectionsr[channel_id]

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
            guild_id = self._connectionsr[channel_id]
        
        try:
            return self._connections[guild_id]
        except KeyError:
            return
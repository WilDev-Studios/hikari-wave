from __future__ import annotations

from dataclasses import dataclass
from hikariwave.audio.ffmpeg import FFmpegPool
from hikariwave.config import Config
from hikariwave.connection import VoiceConnection
from hikariwave.event.factory import EventFactory
from hikariwave.event.types import WaveEventType
from hikariwave.internal.error import GatewayError
from typing import TypeAlias

import asyncio
import hikari
import logging
import os
import shutil

__all__ = ("VoiceClient",)

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

    __slots__ = (
        "_bot", "_config", "_audio_frame_length",
        "_connections", "_connectionsr", "_channels", "_members",
        "_ssrcs", "_ssrcsr", "_states", "_event_factory", "_ffmpeg",
    )

    def __init__(
        self,
        bot: hikari.GatewayBot,
        *,
        config: Config | None = None,
    ) -> None:
        """
        Create a new voice client.
        
        Parameters
        ----------
        bot : hikari.GatewayBot
            The `hikari`-based Discord bot to link this voice system with.
        config : Config | None
            If provided, the global configuration settings.
        
        Raises
        ------
        TypeError
            - If `bot` isn't a `hikari.GatewayBot`.
            - If `config` is provided and isn't `Config`.
        """

        if not isinstance(bot, hikari.GatewayBot):
            error: str = "Provided bot must be a `hikari.GatewayBot`"
            raise TypeError(error)
        
        if config and not isinstance(config, Config):
            error: str = "Provided config must be `Config`"
            raise TypeError(error)
        
        self._bot: hikari.GatewayBot = bot
        self._bot.subscribe(hikari.VoiceStateUpdateEvent, self._disconnected)
        self._bot.subscribe(hikari.VoiceStateUpdateEvent, self._voice_state_update)
        self._bot.subscribe(hikari.StoppingEvent, self.close)
        self._config: Config = config if config else Config()

        self._connections: dict[GuildID, VoiceConnection] = {}
        self._connectionsr: dict[ChannelID, GuildID] = {}

        self._channels: dict[ChannelID, VoiceChannelMeta] = {}
        self._members: dict[MemberID, ChannelID] = {}
        self._ssrcs: dict[MemberID, int] = {}
        self._ssrcsr: dict[int, MemberID] = {}

        self._states: dict[MemberID, tuple[bool, bool]] = {}

        self._event_factory: EventFactory = EventFactory(self._bot)
        self._ffmpeg: FFmpegPool = FFmpegPool()

        if os.path.exists("wavecache"): shutil.rmtree("wavecache")
    
    async def _connect(self, guild_id: hikari.Snowflake, channel_id: hikari.Snowflake, mute: bool, deaf: bool, disconnect: bool = False) -> VoiceConnection:
        try:
            if disconnect:
                await self._disconnect(guild_id)
            
            if guild_id in self._connections and not disconnect:
                return self._connections[guild_id]

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
        except Exception:
            await self._disconnect(guild_id)
            raise

    async def _disconnect(self, guild_id: hikari.Snowflake) -> None:
        if guild_id not in self._connections:
            return
        
        connection: VoiceConnection = self._connections.pop(guild_id)

        logger.info(f"Disconnecting from voice: Guild={guild_id}, Channel={connection._channel_id}")

        del self._connectionsr[connection._channel_id]
        await connection._disconnect()

        cmeta: VoiceChannelMeta = self._channels.pop(connection._channel_id, None)
        if cmeta:
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

        if os.path.exists(f"wavecache/{guild_id}"): shutil.rmtree(f"wavecache/{guild_id}")

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
            self._states.pop(member.id, None)

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

    async def close(self) -> None:
        """
        Shut down every connection and clean up.
        """

        self._bot.unsubscribe(hikari.VoiceStateUpdateEvent, self._disconnected)
        self._bot.unsubscribe(hikari.VoiceStateUpdateEvent, self._voice_state_update)
        self._bot.unsubscribe(hikari.StoppingEvent, self.close)

        await asyncio.gather(
            *(self._disconnect(guild_id) for guild_id in self._connections.keys())
        )

        if self._connections: self._connections.clear()
        if self._connectionsr: self._connectionsr.clear()

        if self._channels: self._channels.clear()
        if self._members: self._members.clear()
        if self._ssrcs: self._ssrcs.clear()
        if self._ssrcsr: self._ssrcsr.clear()

        if self._states: self._states.clear()

        await self._ffmpeg.stop()

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
            If the bot should be muted upon joining the channel.
        deaf : bool
            If the bot should be deafened upon joining the channel.
        
        Returns
        -------
        VoiceConnection
            The active connection to the voice channel, once fully connected.
        
        Raises
        ------
        asyncio.TimeoutError
            If Discord doesn't send a corresponding voice server/state update.
        TypeError
            - If `guild_id` or `channel_id` aren't `hikari.Snowflakeish`.
            - If `mute` or `deaf` aren't `bool`.
        """

        if not isinstance(guild_id, hikari.Snowflakeish):
            error: str = "Provided guild ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if not isinstance(channel_id, hikari.Snowflakeish):
            error: str = "Provided channel ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if not isinstance(mute, bool):
            error: str = "Provided mute state must be of type `bool`"
            raise TypeError(error)
        
        if not isinstance(deaf, bool):
            error: str = "Provided deaf state must be of type `bool`"
            raise TypeError(error)

        return await self._connect(guild_id, channel_id, mute, deaf)
    
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
            The ID of the guild that the channel to disconnect from is in.
        channel_id : hikari.Snowflakeish | None
            The ID of the channel to disconnect from.
        
        Note
        ----
        At least one of `guild_id` or `channel_id` must be provided.

        Raises
        ------
        TypeError
            If `guild_id` or `channel_id` aren't `hikari.Snowflakeish`.
        ValueError
            If neither of `guild_id` or `channel_id` are provided.
        """
        
        if not guild_id and not channel_id:
            error: str = "At least guild_id or channel_id must be defined"
            raise ValueError(error)
        
        if guild_id and not isinstance(guild_id, hikari.Snowflakeish):
            error: str = "Provided guild ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if channel_id and not isinstance(channel_id, hikari.Snowflakeish):
            error: str = "Provided channel ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
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
            The ID of the guild that the connection is handling.
        channel_id : hikari.Snowflakeish | None
            The ID of the channel that the connection is handling.
        
        Note
        ----
        At least one of `guild_id` or `channel_id` must be provided.
        
        Returns
        -------
        VoiceConnection | None
            The active voice connection at the guild/channel, if present.

        Raises
        ------
        TypeError
            If `guild_id` or `channel_id` aren't `hikari.Snowflakeish`.
        ValueError
            If neither of `guild_id` or `channel_id` are provided.
        """

        if not guild_id and not channel_id:
            error: str = "At least guild_id or channel_id must be defined"
            raise ValueError(error)
        
        if guild_id and not isinstance(guild_id, hikari.Snowflakeish):
            error: str = "Provided guild ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if channel_id and not isinstance(channel_id, hikari.Snowflakeish):
            error: str = "Provided channel ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if channel_id:
            guild_id = self._connectionsr[channel_id]
        
        try:
            return self._connections[guild_id]
        except KeyError:
            return
    
    async def move(
        self,
        channel_id: hikari.Snowflakeish,
        *,
        guild_id: hikari.Snowflakeish | None = None,
        old_channel_id: hikari.Snowflakeish | None = None,
        mute: bool = False,
        deaf: bool = True,
    ) -> VoiceConnection:
        """
        Move to another voice channel.
        
        Parameters
        ----------
        channel_id : hikari.Snowflakeish
            The ID of the channel to move to.
        guild_id : hikari.Snowflakeish | None
            The ID of the guild you're currently in.
        old_channel_id : hikari.Snowflakeish | None
            The ID of the channel you're currently in.
        mute : bool 
            If the bot should be muted upon moving channels.
        deaf : bool
            If the bot should be deafened upon moving channels.
        
        Note
        ----
        Either `guild_id` or `old_channel_id` have to be provided.

        Returns
        -------
        VoiceConnection
            The active connection to the new voice channel, once fully connected.
        
        Raises
        ------
        asyncio.TimeoutError
            If Discord doesn't send a corresponding voice server/state update.
        TypeError
            - If `channel_id`, `old_channel_id`, or `guild_id` aren't `hikari.Snowflakeish`.
            - If `mute` or `deaf` aren't `bool`.
        ValueError
            If neither of `guild_id` or `old_channel_id` are provided.
        """

        if not guild_id and not old_channel_id:
            error: str = "Either `guild_id` or `old_channel_id` have to be provided"
            raise ValueError(error)
        
        if not isinstance(channel_id, hikari.Snowflakeish):
            error: str = "Provided channel ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if old_channel_id and not isinstance(old_channel_id, hikari.Snowflakeish):
            error: str = "Provided old channel ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if guild_id and not isinstance(guild_id, hikari.Snowflakeish):
            error: str = "Provided guild ID must be of type `hikari.Snowflakeish`"
            raise TypeError(error)
        
        if not isinstance(mute, bool):
            error: str = "Provided mute state must be of type `bool`"
            raise TypeError(error)
        
        if not isinstance(deaf, bool):
            error: str = "Provided deaf state must be of type `bool`"
            raise TypeError(error)
        
        if old_channel_id:
            guild_id = self._connectionsr[old_channel_id]
        return await self._connect(guild_id, channel_id, mute, deaf, True)
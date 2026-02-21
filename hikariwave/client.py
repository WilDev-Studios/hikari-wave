from __future__ import annotations

from collections.abc import Mapping
from hikariwave.audio.ffmpeg import FFmpegPool
from hikariwave.config import Config
from hikariwave.connection import VoiceConnection
from hikariwave.event.events.bot import (
    BotJoinEvent,
    BotLeaveEvent,
)
from hikariwave.event.factory import EventFactory
from hikariwave.impl.cache import Cache, VoiceChannelMetadata
from hikariwave.internal.error import (
    ClientError,
    GatewayError,
)
from hikariwave.internal.helpers import verify_type
from hikariwave.internal.tasks import TaskManager
from types import MappingProxyType
from typing import ClassVar, TypeAlias

import asyncio
import hikari
import logging
import os
import shutil
import warnings

__all__ = ("VoiceClient",)

ChannelID: TypeAlias = hikari.Snowflake
GuildID:   TypeAlias = hikari.Snowflake

Muted:    TypeAlias = bool
Deafened: TypeAlias = bool

logger: logging.Logger = logging.getLogger("hikari-wave.client")

class VoiceClient:
    """Voice system implementation for `hikari`-based gateway applications."""

    __slots__ = (
        "_bot", "_bot_id",
        "_accepting", "_config", "_cache",
        "_connections", "_connectionsr",
        "_event_factory", "_ffmpeg", "_tasks",
    )

    __instance: ClassVar[VoiceClient | None] = None

    def __init__(
        self,
        bot: hikari.GatewayBot,
        *,
        config: Config | None = None,
    ) -> None:
        """
        Create a new voice system client.

        Parameters
        ----------
        bot : hikari.GatewayBot
            The `hikari`-based gateway application to link this voice system with.
        config : Config | None
            If provided, the global configuration settings.

        Raises
        ------
        ClientError
            If a voice client is already active in this process.
        TypeError
            - If `bot` is not `hikari.GatewayBot`.
            - If provided, `config` is not `Config`.
        """

        if VoiceClient.__instance is not None:
            error: str = "Only one voice client can be active per process"
            raise ClientError(error)

        verify_type(bot, hikari.GatewayBot, "bot")

        if config is not None:
            verify_type(config, Config, "config")

        VoiceClient.__instance = self

        async def bot_started(_) -> None:
            self._accepting = True
            self._bot_id = self._bot.get_me().id
            self._bot.unsubscribe(hikari.StartedEvent, bot_started)

        async def state_update(event: hikari.VoiceStateUpdateEvent) -> None:
            if event.state.user_id != self._bot_id:
                return

            if event.state.channel_id:
                return

            if event.guild_id not in self._connections:
                return

            await self.__disconnect(event.guild_id)

        self._bot: hikari.GatewayBot = bot
        self._bot.subscribe(hikari.StartedEvent, bot_started)
        self._bot.subscribe(hikari.VoiceStateUpdateEvent, state_update)
        self._bot_id: hikari.Snowflake = None

        self._accepting: bool = False
        self._config: Config = config or Config()
        self._cache: Cache = Cache(self)

        self._connections:  dict[GuildID, VoiceConnection] = {}
        self._connectionsr: dict[ChannelID, GuildID] = {}

        self._event_factory: EventFactory = EventFactory(self._bot)
        self._ffmpeg: FFmpegPool = FFmpegPool(self._config._ffmpeg._max_core, self._config._ffmpeg._max_total)
        self._tasks: TaskManager = TaskManager()

        if os.path.exists("wavecache"):
            shutil.rmtree("wavecache")

    async def __connect(
        self,
        guild_id: hikari.Snowflake,
        channel_id: hikari.Snowflake,
        mute: bool,
        deaf: bool,
    ) -> VoiceConnection:
        try:
            if self._config.record and deaf:
                warning: str = "Voice client set to record audio but `deaf` is `True`; audio cannot be received"
                logger.warning(warning)
                warnings.warn(warning, RuntimeWarning, 1)

            await self._bot.update_voice_state(guild_id, channel_id, self_mute=mute, self_deaf=deaf)

            try:
                server_update, state_update = await asyncio.gather(
                    self._bot.wait_for(
                        hikari.VoiceServerUpdateEvent, 3.0,
                        lambda e: e.guild_id == guild_id,
                    ),
                    self._bot.wait_for(
                        hikari.VoiceStateUpdateEvent, 3.0,
                        lambda e: e.guild_id == guild_id and e.state.channel_id == channel_id and e.state.user_id == self._bot_id,
                    )
                )
            except asyncio.TimeoutError as e:
                error: str = "Voice server/state update timed out"
                raise GatewayError(error) from e

            bot_id: hikari.Snowflake = self._bot_id
            guild: hikari.Guild = await self._bot.rest.fetch_guild(guild_id)
            members: dict[hikari.Snowflake, hikari.Member] = {}

            for state in guild.get_voice_states().values():
                if state.user_id == bot_id or state.channel_id != channel_id:
                    continue

                self._cache.set_member_state(
                    state.user_id,
                    state.is_guild_muted or state.is_self_muted,
                    state.is_guild_deafened or state.is_self_deafened,
                )

                members[state.user_id] = state.member
                self._cache.set_member_channel(state.user_id, channel_id)

            self._cache.set_channel_metadata(channel_id, VoiceChannelMetadata(set(), guild_id, channel_id, members))

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
                BotJoinEvent,
                bot=self._bot,
                channel_id=channel_id,
                guild_id=guild_id,
                is_deaf=deaf,
                is_mute=mute,
            )

            return connection
        except Exception:
            await self.__disconnect(guild_id)
            raise

    async def __disconnect(
        self,
        guild_id: hikari.Snowflake,
    ) -> None:
        if guild_id not in self._connections:
            return

        connection: VoiceConnection = self._connections.pop(guild_id)
        del self._connectionsr[connection.channel_id]

        metadata: VoiceChannelMetadata = self._cache.delete_channel_metadata(connection._channel_id)
        if metadata:
            for member_id in metadata.members.keys():
                self._cache.delete_member(member_id)
                self._cache.delete_ssrc(member_id)

        self._event_factory.emit(
            BotLeaveEvent,
            bot=self._bot,
            channel_id=connection._channel_id,
            guild_id=guild_id,
        )

        await connection._disconnect()

    @property
    def bot(self) -> hikari.GatewayBot:
        """The linked `hikari`-based gateway application."""
        return self._bot

    async def close(self) -> None:
        """
        Disconnect each connection and clean up.
        """

        self._accepting = False

        logger.info("Voice client signalled to shut down; disconnecting and cleaning up...")

        await asyncio.gather(
            *(self.__disconnect(guild_id) for guild_id in self._connections.keys())
        )

        if self._connectionsr:
            self._connectionsr.clear()

        if self._connections:
            self._connections.clear()

        self._cache.clear()

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
            The ID of the guild to connect to.
        channel_id : hikari.Snowflakeish
            The ID of the voice channel to connect to.
        mute : bool
            If the bot should be muted upon joining the voice channel.
        deaf : bool
            If the bot should be deafened upon joining the voice channel.

        Returns
        -------
        VoiceConnection
            Once fully connected, the active voice connection to this guild/channel.

        Raises
        ------
        asyncio.TimeoutError
            If Discord fails to send a corresponding voice server/state update.
        ClientError
            - If the voice client isn't able to open new connections.
            - If an active connection to this guild/channel already exists.
        TypeError
            - If `guild_id` or `channel_id` are not `hikari.Snowflakeish`.
            - If `mute` or `deaf` are not `bool`.
        """

        if not self._accepting:
            error: str = "The voice client isn't able to open new connections currently"
            raise ClientError(error)

        verify_type(guild_id, hikari.Snowflakeish, "guild_id")
        verify_type(channel_id, hikari.Snowflakeish, "channel_id")
        verify_type(mute, bool, "mute")
        verify_type(deaf, bool, "deaf")

        guild_id: hikari.Snowflake = hikari.Snowflake(guild_id)
        channel_id: hikari.Snowflake = hikari.Snowflake(channel_id)

        if guild_id in self._connections:
            error: str = "An active connection to this guild/channel already exists"
            raise ClientError(error)

        logger.info(
            f"Connecting to a voice channel: GuildID={guild_id}, ChannelID={channel_id}, Mute={mute}, Deaf={deaf}"
        )

        return await self.__connect(guild_id, channel_id, mute, deaf)

    @property
    def connections(self) -> Mapping[GuildID, VoiceConnection]:
        """A live view of all active voice connections."""
        return MappingProxyType(self._connections)

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
            If provided, the ID of the guild that is connected.
        channel_id : hikari.Snowflakeish | None
            If provided, the ID of the voice channel that is connected.

        Note
        ----
        Either `guild_id` or `channel_id` must be provided.

        Raises
        ------
        ClientError
            If no active connection to the guild/channel exists.
        TypeError
            If `guild_id` or `channel_id` are not `hikari.Snowflakeish`.
        ValueError
            If neither `guild_id` nor `channel_id` are provided.
        """

        if guild_id is None and channel_id is None:
            error: str = "A guild ID or channel ID must be provided"
            raise ValueError(error)

        if guild_id is not None:
            verify_type(guild_id, hikari.Snowflakeish, "guild_id")

        if channel_id is not None:
            verify_type(channel_id, hikari.Snowflakeish, "channel_id")

        if channel_id:
            guild_id = self._connectionsr.get(hikari.Snowflake(channel_id))

        if guild_id is None:
            error: str = "No active connection to the guild/channel exists"
            raise ClientError(error)

        logger.info(
            f"Disconnecting from voice channel: GuildID={guild_id}, ChannelID={channel_id}"
        )

        await self.__disconnect(hikari.Snowflake(guild_id))

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
            If provided, the ID of the guild that is connected.
        channel_id : hikari.Snowflakeish | None
            If provided, the ID of the voice channel that is connected.

        Note
        ----
        Either `guild_id` or `channel_id` must be provided.

        Returns
        -------
        VoiceConnection | None
            If found, the active voice connection to the guild/channel.

        Raises
        ------
        TypeError
            If `guild_id` or `channel_id` are not `hikari.Snowflakeish`.
        ValueError
            If neither `guild_id` nor `channel_id` are provided.
        """

        if guild_id is None and channel_id is None:
            error: str = "A guild ID or channel ID must be provided"
            raise ValueError(error)

        if guild_id:
            verify_type(guild_id, hikari.Snowflakeish, "guild_id")

        if channel_id:
            verify_type(channel_id, hikari.Snowflakeish, "channel_id")

        if channel_id:
            guild_id = self._connectionsr.get(hikari.Snowflake(channel_id))

        return self._connections.get(hikari.Snowflake(guild_id))

    async def move(
        self,
        new_channel_id: hikari.Snowflakeish,
        *,
        guild_id: hikari.Snowflakeish | None = None,
        old_channel_id: hikari.Snowflakeish | None = None,
        mute: bool = False,
        deaf: bool = True,
    ) -> VoiceConnection:
        """
        Move to another voice channel (disconnect from old, connect to new).

        Parameters
        ----------
        new_channel_id : hikari.Snowflakeish
            The ID of the new voice channel to move to (connect).
        guild_id : hikari.Snowflakeish | None
            If provided, the ID of the guild of the connection.
        old_channel_id : hikari.Snowflakeish | None
            If provided, the ID of the old voice channel to move from (disconnect).
        mute : bool | None
            If the bot should be muted upon moving channels.
        deaf : bool | None
            If the bot should be deafened upon moving channels.

        Note
        ----
        Either `guild_id` or `old_channel_id` must be provided.

        Returns
        -------
        VoiceConnection
            Once fully connected, the active voice connection to this guild/new channel.

        Raises
        ------
        asyncio.TimeoutError
            If Discord fails to send a corresponding voice server/state update.
        ClientError
            - If the voice client isn't able to open new connections.
            - If no active voice connection already exists.
        TypeError
            - If `new_channel_id`, `guild_id`, or `old_channel_id` are not `hikari.Snowflakeish`.
            - If `mute` or `deaf` are not `bool`.
        ValueError
            If neither of `guild_id` nor `old_channel_id` are provided.
        """

        if not self._accepting:
            error: str = "The voice client isn't able to open new connections currently"
            raise ClientError(error)

        if guild_id is None and old_channel_id is None:
            error: str = "A guid ID or old channel ID must be provided"
            raise ValueError(error)

        verify_type(new_channel_id, hikari.Snowflakeish, "new_channel_id")

        if guild_id is not None:
            verify_type(guild_id, hikari.Snowflakeish, "guild_id")

        if old_channel_id is not None:
            verify_type(old_channel_id, hikari.Snowflakeish, "old_channel_id")

        if mute is not None:
            verify_type(mute, bool, "mute")

        if deaf is not None:
            verify_type(deaf, bool, "deaf")

        if old_channel_id:
            guild_id = self._connectionsr.get(hikari.Snowflake(old_channel_id))

        guild_id: hikari.Snowflake = hikari.Snowflake(guild_id)
        connection: VoiceConnection = self._connections.get(guild_id)

        if not connection:
            error: str = "No active connection to the guild/channel exists"
            raise ClientError(error)

        logger.info(
            f"Moving voice channels: GuildID={guild_id}, NewChannelID={new_channel_id}, OldChannelID={connection.channel_id}"
        )

        await self.__disconnect(guild_id)
        return await self.__connect(
            guild_id,
            new_channel_id,
            mute,
            deaf,
        )

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from hikariwave.audio.player import AudioPlayer
from hikariwave.config import Config
from hikariwave.internal.constants import Constants, Opcode
from hikariwave.internal.dev import log_exception
from hikariwave.internal.encrypt import Encrypt
from hikariwave.networking.gateway import GatewayReadyPayload, GatewaySessionDescriptionPayload, VoiceGateway
from hikariwave.networking.server import VoiceServer
from typing import TYPE_CHECKING

import asyncio
import hikari

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

__all__ = ("VoiceConnection",)

class ConnectionStatus(IntEnum):
    """Represents the current state of a voice connection."""

    CONNECTED    = 0
    """Connected to voice gateway and voice server."""
    CONNECTING   = 1
    """Connecting to voice gateway and voice server."""
    DISCONNECTED = 2
    """Disconnected from voice gateway and voice server."""
    NEW          = 3
    """Instantiated and waiting to begin connection."""
    RECONNECTING = 4
    """Reconnecting to voice gateway and voice server."""

class VoiceConnection:
    """An active connection to a Discord voice channel."""

    __slots__ = (
        "_client", "_guild_id", "_channel_id", "_endpoint", "_session_id", "_token", "_config",
        "_server", "_gateway", "_ready", "_state", "_ssrc", "_encryption_mode", "_decryption_mode",
        "_secret", "_player",
    )

    def __init__(
        self,
        client: VoiceClient,
        guild_id: hikari.Snowflake,
        channel_id: hikari.Snowflake,
        endpoint: str,
        session_id: str,
        token: str,
    ) -> None:
        """
        Create a new voice connection.

        Parameters
        ----------
        client : VoiceClient
            The controlling client for all connections and state.
        guild_id : hikari.Snowflake
            The ID of the guild the channel is in.
        channel_id : hikari.Snowflake
            The ID of the channel to connect to.
        endpoint : str
            The URL of Discord's voice gateway.
        session_id : str
            The provided session ID from Discord's OAuth2 gateway.
        token : str
            The provided token from Discord's OAuth2 gateway.
        """

        self._client: VoiceClient = client
        self._guild_id: hikari.Snowflake = guild_id
        self._channel_id: hikari.Snowflake = channel_id
        self._endpoint: str = endpoint
        self._session_id: str = session_id
        self._token: str = token
        self._config: Config = self._client._config

        self._server: VoiceServer = VoiceServer(self)
        self._gateway: VoiceGateway = VoiceGateway(
            self,
            self._guild_id,
            self._channel_id,
            self._client.bot.get_me().id,
            self._session_id,
            self._token,
        )
        self._gateway.set_callback(Opcode.READY, self.__gateway_ready)
        self._gateway.set_callback(Opcode.SESSION_DESCRIPTION, self.__gateway_session_description)
        self._ready: asyncio.Event = asyncio.Event()
        self._state: ConnectionStatus = ConnectionStatus.NEW

        self._ssrc: int = None
        self._encryption_mode: Callable[[bytes, int, bytes, bytes], bytes] = None
        self._decryption_mode: Callable[[bytes, bytes], bytes] = None
        self._secret: bytes = None

        self._player: AudioPlayer = AudioPlayer(self)

        self._client._bot.subscribe(hikari.VoiceServerUpdateEvent, self.__server_update)

    async def __gateway_ready(self, payload: GatewayReadyPayload) -> None:
        self._ssrc = payload.ssrc

        chosen_mode: str = None
        for mode in payload.modes:
            if mode not in Encrypt.SUPPORTED:
                continue

            chosen_mode = mode
            break

        if not chosen_mode:
            error: str = "No supported encryption method was found/implemented"
            raise RuntimeError(error)

        ip, port = await self._server.connect(payload.ip, payload.port, self._ssrc)

        await self._gateway.select_protocol(ip, port, chosen_mode)

    async def __gateway_session_description(self, payload: GatewaySessionDescriptionPayload) -> None:
        self._encryption_mode = getattr(Encrypt, f"encrypt_{payload.mode}")
        self._decryption_mode = getattr(Encrypt, f"decrypt_{payload.mode}")
        self._secret = payload.secret
        self._state = ConnectionStatus.CONNECTED

        self._ready.set()

        if not self._player._resume_event.is_set() and self._player._current:
            await self._player.resume()

    async def __server_update(self, event: hikari.VoiceServerUpdateEvent) -> None:
        if not event.endpoint:
            await self._disconnect()
            return

        self._endpoint = event.endpoint
        self._gateway = VoiceGateway(
            self,
            self._guild_id,
            self._channel_id,
            self._client._bot.get_me().id,
            self._session_id,
            event.token,
        )
        await self._connect()

    async def _connect(self) -> None:
        if self._state in (ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING):
            return

        self._state = ConnectionStatus.CONNECTING
        self._ready.clear()

        try:
            await self._gateway.connect(f"{self._endpoint}/?v={Constants.GATEWAY_VERSION}")
            await self._ready.wait()

            if self._state == ConnectionStatus.CONNECTING:
                self._state = ConnectionStatus.CONNECTED
        except Exception as e:
            log_exception(e)

            self._state = ConnectionStatus.NEW
            raise

    async def _disconnect(self) -> None:
        if self._state == ConnectionStatus.DISCONNECTED:
            return

        self._state = ConnectionStatus.DISCONNECTED

        if self._player:
            await self._player.stop()

        if self._server:
            await self._server.disconnect()

        if self._gateway:
            await self._gateway.disconnect()

    @property
    def channel_id(self) -> hikari.Snowflake:
        """The ID of the channel this connection is in."""
        return self._channel_id

    @property
    def client(self) -> hikari.GatewayBot:
        """The controlling OAuth2 bot."""
        return self._client

    async def disconnect(self) -> None:
        """
        Disconnect from the current channel.
        """

        self._client._bot.unsubscribe(hikari.VoiceServerUpdateEvent, self.__server_update)
        await self._client.disconnect(self._guild_id)

    @property
    def guild_id(self) -> hikari.Snowflake:
        """The ID of the guild this connection is in."""
        return self._guild_id

    @property
    def latency(self) -> float | None:
        """Get the heartbeat latency of this connection with Discord's gateway, if connected."""

        if not self._gateway._heartbeat_ack:
            return None

        return self._gateway._heartbeat_ack - self._gateway._heartbeat_sent

    @property
    def player(self) -> AudioPlayer:
        """The audio player associated with this connection."""
        return self._player

    def set_config(self, config: Config) -> None:
        """
        Set this specific connection's configuration.

        Parameters
        ----------
        config : Config
            This connections configuration.

        Raises
        ------
        TypeError
            If the provided config isn't `Config`.
        """

        if not isinstance(config, Config):
            error: str = "The provided config must be `Config`"
            raise TypeError(error)

        self._config = config

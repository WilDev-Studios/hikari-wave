from __future__ import annotations

from enum import auto, IntEnum
from hikariwave.audio.player import AudioPlayer
from hikariwave.event.types import WaveEventType
from hikariwave.internal.encrypt import Encrypt
from hikariwave.networking.gateway import Opcode, ReadyPayload, SessionDescriptionPayload, VoiceGateway
from hikariwave.networking.server import VoiceServer
from typing import Callable, TYPE_CHECKING

import asyncio
import hikari

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

__all__ = ("VoiceConnection",)

class ConnectionStatus(IntEnum):
    """Represents the current state of a voice connection."""

    CONNECTED = auto()
    """Connected to voice gateway and voice server."""
    CONNECTING = auto()
    """Connecting to voice gateway and voice server."""
    DISCONNECTED = auto()
    """Disconnected from voice gateway and voice server."""
    NEW = auto()
    """Instantiated and waiting to begin connection."""
    RECONNECTING = auto()
    """Reconnecting to voice gateway and voice server."""

class VoiceConnection:
    """An active connection to a Discord voice channel."""

    __slots__ = (
        "_client", "_guild_id", "_channel_id", "_endpoint", "_session_id", "_token",
        "_server", "_gateway", "_ready", "_state", "_ssrc", "_mode", "_secret", "_player",
    )

    def __init__(
        self,
        client: VoiceClient,
        guild_id: hikari.Snowflakeish,
        channel_id: hikari.Snowflakeish,
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
        guild_id : hikari.Snowflakeish
            The ID of the guild the channel is in.
        channel_id : hikari.Snowflakeish
            The ID of the channel to connect to.
        endpoint : str
            The URL of Discord's voice gateway.
        session_id : str
            The provided session ID from Discord's OAuth2 gateway.
        token : str
            The provided token from Discord's OAuth2 gateway.
        """
        
        self._client: VoiceClient = client
        self._guild_id: hikari.Snowflakeish = guild_id
        self._channel_id: hikari.Snowflakeish = channel_id
        self._endpoint: str = endpoint
        self._session_id: str = session_id
        self._token: str = token

        self._server: VoiceServer = VoiceServer(self._client)
        self._gateway: VoiceGateway = VoiceGateway(
            self,
            self._guild_id,
            self._channel_id,
            self._client.bot.get_me().id,
            self._session_id,
            self._token,
        )
        self._gateway.set_callback(Opcode.READY, self._gateway_ready)
        self._gateway.set_callback(Opcode.SESSION_DESCRIPTION, self._gateway_session_description)
        self._ready: asyncio.Event = asyncio.Event()
        self._state: ConnectionStatus = ConnectionStatus.NEW

        self._ssrc: int = None
        self._mode: Callable[[bytes, int, bytes, bytes], bytes] = None
        self._secret: bytes = None

        self._player: AudioPlayer = AudioPlayer(self)
    
    async def _connect(self) -> None:
        if self._state in (ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING):
            return
        
        self._state = ConnectionStatus.CONNECTING
        self._ready.clear()

        try:
            await self._gateway.connect(f"{self._endpoint}/?v=8")
            await self._ready.wait()

            if self._state == ConnectionStatus.CONNECTING:
                self._state = ConnectionStatus.CONNECTED
        except Exception:
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

    async def _gateway_ready(self, payload: ReadyPayload) -> None:
        self._ssrc = payload.ssrc
        
        supported_modes: list[str] = payload.modes
        chosen_mode: str = None
        for mode in supported_modes:
            if mode not in Encrypt.SUPPORTED:
                continue

            if not hasattr(Encrypt, mode):
                continue

            chosen_mode = mode
            break

        if not chosen_mode:
            error: str = "No supported encryption method was found/implemented"
            raise RuntimeError(error)

        ip, port = await self._server.connect(payload.ip, payload.port, self._ssrc)

        await self._gateway.select_protocol(ip, port, chosen_mode)

    async def _gateway_reconnect(self) -> None:
        if self._state == ConnectionStatus.RECONNECTING:
            return
        
        self._state = ConnectionStatus.RECONNECTING
        self._ready.clear()

        if self._player and self._player.is_playing:
            await self._player.pause()
    
        await self._server.disconnect()
        await self._gateway.disconnect()

        self._server = VoiceServer(self._client)
        self._gateway = VoiceGateway(
            self,
            self._guild_id,
            self._channel_id,
            self._client.bot.get_me().id,
            self._session_id,
            self._token,
        )
        self._gateway.set_callback(Opcode.READY, self._gateway_ready)
        self._gateway.set_callback(Opcode.SESSION_DESCRIPTION, self._gateway_session_description)
        await self._gateway.connect(f"{self._endpoint}/?v=8")

        self._client._event_factory.emit(
            WaveEventType.VOICE_RECONNECT,
            self._channel_id,
            self._guild_id,
        )

    async def _gateway_session_description(self, payload: SessionDescriptionPayload) -> None:
        self._mode = getattr(Encrypt, payload.mode)
        self._secret = payload.secret
        self._state = ConnectionStatus.CONNECTED

        self._ready.set()

        if not self._player._resumed.is_set() and self._player._current:
            await self._player.resume()

    @property
    def channel_id(self) -> hikari.Snowflakeish:
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
        
        await self._client.disconnect(self._guild_id)
    
    @property
    def guild_id(self) -> hikari.Snowflakeish:
        """The ID of the guild this connection is in."""
        return self._guild_id

    @property
    def latency_gateway(self) -> float | None:
        """Get the heartbeat latency of this connection with Discord's gateway, if connected."""
        
        if not self._gateway._last_heartbeat_ack:
            return None
        
        return self._gateway._last_heartbeat_ack - self._gateway._last_heartbeat_sent
    
    @property
    def player(self) -> AudioPlayer:
        """The audio player associated with this connection."""
        return self._player

from __future__ import annotations

from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source import AudioSource
from hikariwave.event.types import WaveEventType
from hikariwave.networking.gateway import Opcode, ReadyPayload, SessionDescriptionPayload, VoiceGateway
from hikariwave.networking.server import VoiceServer
from typing import TYPE_CHECKING

import asyncio
import hikari

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

__all__ = ("VoiceConnection",)

class VoiceConnection:
    """An active connection to a Discord voice channel."""

    __slots__ = (
        "_client", "_guild_id", "_channel_id", "_endpoint", "_session_id", "_token",
        "_server", "_gateway", "_ready", "_ssrc", "_mode", "_secret", "_player",
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

        self._ssrc: int = None
        self._mode: str = None
        self._secret: bytes = None

        self._player: AudioPlayer = AudioPlayer(self)
    
    async def _connect(self) -> None:
        await self._gateway.connect(f"{self._endpoint}/?v=8")
        await self._ready.wait()

    async def _disconnect(self) -> None:
        await self._server.disconnect()
        await self._gateway.disconnect()

    async def _gateway_ready(self, payload: ReadyPayload) -> None:
        self._ssrc = payload.ssrc
        
        supported_mode: str = "aead_xchacha20_poly1305_rtpsize"
        ip, port = await self._server.connect(payload.ip, payload.port, self._ssrc)

        await self._gateway.select_protocol(ip, port, supported_mode)

    async def _gateway_reconnect(self) -> None:
        self._gateway = VoiceGateway(
            self,
            self._guild_id,
            self._channel_id,
            self._client.bot.get_me().id,
            self._session_id,
            self._token,
        )
        await self._gateway.connect(f"{self._endpoint}/?v=8")

        self._client._event_factory.emit(
            WaveEventType.VOICE_RECONNECT,
            self._channel_id,
            self._guild_id,
        )

    async def _gateway_session_description(self, payload: SessionDescriptionPayload) -> None:
        self._mode = payload.mode
        self._secret = payload.secret
        self._ready.set()
    
    async def add_queue(self, source: AudioSource) -> None:
        """
        Add an audio source to the player's queue.
        
        Parameters
        ----------
        source : AudioSource
            The source to add to the queue.
        """

        await self._player.add_queue(source)
    
    @property
    def channel_id(self) -> hikari.Snowflakeish:
        """The ID of the channel this connection is in."""
        return self._channel_id

    async def clear_queue(self) -> None:
        """
        Clear audio from the player's queue.
        """

        await self._player.clear_queue()

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
    def latency_gateway(self) -> float:
        """Get the heartbeat latency of this connection with Discord's gateway."""
        
        return self._gateway._last_heartbeat_ack - self._gateway._last_heartbeat_sent
    
    async def next(self) -> None:
        """
        Play the next audio in queue.
        """

        await self._player.next()

    async def pause(self) -> None:
        """
        Pause playback of the current audio.
        """
        
        await self._player.pause()

    async def play(self, source: AudioSource) -> None:
        """
        Play audio from a source.
        
        Parameters
        ----------
        source : AudioSource
            The source that contains the audio.
        """

        await self._player.play(source)
    
    @property
    def player(self) -> AudioPlayer:
        """The audio player associated with this connection."""
        return self._player

    async def previous(self) -> None:
        """
        Play the latest previously played audio.
        """

        await self._player.previous()

    async def remove_queue(self, source: AudioSource) -> None:
        """
        Remove an audio source from the player's queue.
        
        Parameters
        ----------
        source : AudioSource
            The source to remove from the queue.
        """

        await self._player.remove_queue(source)
    
    async def resume(self) -> None:
        """
        Resume playback of the current audio.
        """
        
        await self._player.resume()
    
    async def shuffle(self) -> None:
        """
        Shuffle all audio in the player's queue.
        """

        await self._player.shuffle()

    async def stop(self) -> None:
        """
        Stop playback of the current audio.
        """
        
        await self._player.stop()
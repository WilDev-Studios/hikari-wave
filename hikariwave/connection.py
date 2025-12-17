from __future__ import annotations

from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source import AudioSource, FileAudioSource
from hikariwave.event.types import WaveEventType
from hikariwave.gateway import Opcode, ReadyPayload, SessionDescriptionPayload, VoiceGateway
from hikariwave.server import VoiceServer
from typing import Final, Sequence, TYPE_CHECKING

import asyncio
import hikari

if TYPE_CHECKING:
    from .client import VoiceClient

__all__: Final[Sequence[str]] = ("VoiceConnection",)

class VoiceConnection:
    """An active connection to a Discord voice channel."""

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
        
        self.client: VoiceClient = client
        self.guild_id: hikari.Snowflakeish = guild_id
        self.channel_id: hikari.Snowflakeish = channel_id
        self.endpoint: str = endpoint
        self.session_id: str = session_id
        self.token: str = token

        self.server: VoiceServer = VoiceServer(self.client)
        self.gateway: VoiceGateway = VoiceGateway(
            self,
            self.guild_id,
            self.channel_id,
            self.client.bot.get_me().id,
            self.session_id,
            self.token,
        )
        self.gateway.set_callback(Opcode.READY, self._gateway_ready)
        self.gateway.set_callback(Opcode.SESSION_DESCRIPTION, self._gateway_session_description)
        self.ready: asyncio.Event = asyncio.Event()

        self.ssrc: int = None
        self.mode: str = None

        self.player: AudioPlayer = AudioPlayer(self)
    
    async def _connect(self) -> None:
        await self.gateway.connect(f"{self.endpoint}/?v=8")
        await self.ready.wait()

    async def _disconnect(self) -> None:
        await self.server.disconnect()
        await self.gateway.disconnect()

    async def _gateway_ready(self, payload: ReadyPayload) -> None:
        self.ssrc = payload.ssrc
        
        supported_mode: str = "aead_xchacha20_poly1305_rtpsize"
        ip, port = await self.server.connect(payload.ip, payload.port, self.ssrc)

        await self.gateway.select_protocol(ip, port, supported_mode)

    async def _gateway_reconnect(self) -> None:
        self.gateway = VoiceGateway(
            self,
            self.guild_id,
            self.channel_id,
            self.client.bot.get_me().id,
            self.session_id,
            self.token,
        )
        await self.gateway.connect(f"{self.endpoint}/?v=8")

        self.client.event_factory.emit(
            WaveEventType.VOICE_RECONNECT,
            self.channel_id,
            self.guild_id,
        )

    async def _gateway_session_description(self, payload: SessionDescriptionPayload) -> None:
        self.mode = payload.mode
        self.secret = payload.secret
        self.ready.set()
    
    async def add_queue(self, source: AudioSource) -> None:
        """
        Add an audio source to the player's queue.
        
        Parameters
        ----------
        source : AudioSource
            The source to add to the queue.
        """

        await self.player.add_queue(source)
    
    async def add_queue_file(self, filepath: str) -> None:
        """
        Add audio to the player's queue from an audio file.
        
        Parameters
        ----------
        filepath : str
            The path, absolute or relative, to the audio file.
        """

        source: FileAudioSource = FileAudioSource(filepath)
        await self.add_queue(source)

    async def clear_queue(self) -> None:
        """
        Clear audio from the player's queue.
        """

        await self.player.clear_queue()

    async def disconnect(self) -> None:
        """
        Disconnect from the current channel.
        """
        
        await self.client.disconnect(self.guild_id)
    
    @property
    def latency_gateway(self) -> float:
        """Get the heartbeat latency of this connection with Discord's gateway."""
        
        return self.gateway.last_heartbeat_ack - self.gateway.last_heartbeat_sent
    
    async def next(self) -> None:
        """
        Play the next audio in queue.
        """

        await self.player.next()

    async def pause(self) -> None:
        """
        Pause playback of the current audio.
        """
        
        await self.player.pause()

    async def play(self, source: AudioSource) -> None:
        """
        Play audio from a source.
        
        Parameters
        ----------
        source : AudioSource
            The source that contains the audio.
        """

        await self.player.play(source)

    async def play_file(self, filepath: str) -> None:
        """
        Play audio from a file.
        
        Parameters
        ----------
        filepath : str
            The path, absolute or relative, to the file to play.
        """
        
        source: FileAudioSource = FileAudioSource(filepath)
        await self.play(source)
    
    async def previous(self) -> None:
        """
        Play the latest previously played audio.
        """

        await self.player.previous()

    async def remove_queue(self, source: AudioSource) -> None:
        """
        Remove an audio source from the player's queue.
        
        Parameters
        ----------
        source : AudioSource
            The source to remove from the queue.
        """

        await self.player.remove_queue(source)
    
    async def remove_queue_file(self, filepath: str) -> None:
        """
        Remove a file audio source from the player's queue.
        
        Parameters
        ----------
        filepath : str
            The path, absolute or relative, to the audio file.
        """

        source: FileAudioSource = FileAudioSource(filepath)
        await self.remove_queue(source)

    async def resume(self) -> None:
        """
        Resume playback of the current audio.
        """
        
        await self.player.resume()
    
    async def stop(self) -> None:
        """
        Stop playback of the current audio.
        """
        
        await self.player.stop()
from __future__ import annotations

from dataclasses import dataclass, field
from hikariwave import voice
from hikariwave.audio.encryption import EncryptionMode
from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source.base import AudioSource
from hikariwave.audio.source.silent import SilentAudioSource
from hikariwave.internal import constants
from hikariwave.protocol import VoiceClientProtocol
from typing import Union

import aiohttp
import asyncio
import hikari
import hikariwave.error as errors
import logging
import time
import typing

if typing.TYPE_CHECKING:
    from typing import Callable

__all__: typing.Sequence[str] = (
    "PendingConnection",
    "VoiceConnection",
)

_logger: logging.Logger = logging.getLogger("hikariwave.connection")


@dataclass
class PendingConnection:
    """A pending connection to a Discord voice server."""

    endpoint: Union[str, None] = field(default=None)
    """The endpoint in which this connection should connect to when activated."""

    session_id: Union[str, None] = field(default=None)
    """The ID of the session provided by Discord that should be used to connect to/resume a session."""

    token: Union[str, None] = field(default=None)
    """The token provided by Discord that should be used to identify when connecting."""


class VoiceConnection:
    """
    An active connection to a Discord voice server.

    Warning
    -------
    This is an internal object and should not be instantiated.
    """

    def __init__(self, bot: hikari.GatewayBot, bot_id: hikari.Snowflake, guild_id: hikari.Snowflake) -> None:
        """Instantiate a new active voice connection.

        Warning
        -------
        - This object should only be instantiated internally.
        - Instantiating this object may cause issues.

        Parameters
        ----------
        bot : hikari.GatewayBot
            The bot instance to interface with.
        bot_id : hikari.Snowflake
            The ID of the bot provided.
        guild_id : hikari.Snowflake
            The ID of the guild that this connection is responsible for.
        """
        self._bot: hikari.GatewayBot = bot
        self._bot_id: hikari.Snowflake = bot_id
        self._guild_id: hikari.Snowflake = guild_id

        self._endpoint: Union[str, None] = None
        self._session_id: Union[str, None] = None
        self._token: Union[str, None] = None

        self._websocket: Union[aiohttp.ClientWebSocketResponse, None] = None
        self._ws_sequence: int = 0
        self._running: bool = False

        self._heartbeat_task: Union[asyncio.Task[None], None] = None
        self._heartbeat_interval: float = 0.0
        self._heartbeat_last_sent: float = time.time()
        self._heartbeat_latency: float = 0.0

        self._ssrc: Union[int, None] = None
        self._ip: Union[str, None] = None
        self._port: Union[int, None] = None
        self._mode: Union[voice.EncryptionType, None] = None

        self._timestamp: Union[int, None] = None
        self._sequence: Union[int, None] = None

        self._protocol: Union[asyncio.DatagramProtocol, None] = None
        self._transport: Union[asyncio.DatagramTransport, None] = None

        self._external_address_discovered: asyncio.Event = asyncio.Event()
        self._external_ip: Union[str, None] = None
        self._external_port: Union[int, None] = None

        self._secret_key: Union[bytes, None] = None
        self._ready_to_send: asyncio.Event = asyncio.Event()

        self._encryption: Union[EncryptionMode, None] = None
        self._player: Union[AudioPlayer, None] = None

    async def _heartbeat_loop(self) -> None:
        while self._running and self._websocket:
            await asyncio.sleep(self._heartbeat_interval)

            heartbeat: voice.VoicePayload[voice.Heartbeat] = voice.VoicePayload(
                op=voice.VoiceCode.HEARTBEAT,
                d=voice.Heartbeat(
                    int(time.time() * 1000),
                    self._ws_sequence,
                ),
            )

            await self._websocket.send_str(voice.encode(heartbeat).decode("UTF-8"))
            self._heartbeat_last_sent = time.time()

    async def _set_speaking(self, speaking: bool) -> None:
        if not self._websocket:
            return

        payload = voice.VoicePayload(
            voice.VoiceCode.SPEAKING,
            voice.Speaking(
                voice.SpeakingType.MICROPHONE if speaking else voice.SpeakingType.NONE,
                0,
                self._ssrc if self._ssrc else 0,
            ),
        )

        await self._websocket.send_str(voice.encode(payload).decode("UTF-8"))

        _logger.debug("Set speaking mode to %s", str(speaking).upper())

    async def _websocket_handler(self) -> None:
        async with aiohttp.ClientSession() as session:
            self._websocket = await session.ws_connect(
                f"wss://{self._endpoint}/?v={constants.WEBSOCKET_VERSION}",
            )

            identify = voice.VoicePayload(
                voice.VoiceCode.IDENTIFY,
                voice.Identify(
                    self._guild_id,
                    self._bot_id,
                    self._session_id if self._session_id else '',
                    self._token if self._token else '',
                ),
            )

            await self._websocket.send_str(voice.encode(identify).decode("UTF-8"))

            try:
                async for message in self._websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._websocket_message(message)
                    elif message.type in [aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR]:
                        _logger.debug(f"Connection flagged to close by websocket")
            except Exception as e:
                _logger.error(e)
            finally:
                _logger.debug("Connection with SESSION_ID: %s closed", self._session_id)

    async def _websocket_message(self, message: aiohttp.WSMessage) -> None:
        payload = voice.decode(message.data)

        if payload.op == voice.VoiceCode.UNKNOWN:
            return

        data = payload.d

        if isinstance(data, voice.Ready):
            _logger.debug("Received `READY` payload - Discovering IP")

            self._ssrc = data.ssrc
            self._ip = data.ip
            self._port = data.port

            for mode in data.modes:
                encryption_mode: Union[Callable[[bytes, bytes], bytes], None] = getattr(
                    EncryptionMode,
                    mode,
                    None,
                )

                if encryption_mode:
                    self._mode = mode
                    break

            if not self._mode:
                error: str = "No supported encryption mode was found"
                raise errors.EncryptionModeNotSupportedError(error)

            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

            def on_ip_discovered(ip: str, port: int) -> None:
                self._external_ip = ip
                self._external_port = port
                self._external_address_discovered.set()

                _logger.debug("External IP discovered - %s:%s", ip, port)

            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: VoiceClientProtocol(self._ssrc if self._ssrc else 0, on_ip_discovered),
                remote_addr=(self._ip, self._port),
            )

            await self._external_address_discovered.wait()

            select_protocol = voice.VoicePayload(
                voice.VoiceCode.SELECT_PROTOCOL,
                voice.SelectProtocol(
                    "udp",
                    voice.SelectProtocolData(
                        self._external_ip if self._external_ip else '',
                        self._external_port if self._external_port else 0,
                        self._mode,
                    ),
                ),
            )

            if not self._websocket:
                return

            await self._websocket.send_str(
                voice.encode(select_protocol).decode("UTF-8"),
            )
            return

        if isinstance(data, voice.Resumed):
            _logger.debug("Session resumed after disconnect")
            return

        if isinstance(data, voice.SessionDescription):
            self._secret_key = bytes(data.secret_key)
            self._encryption = EncryptionMode(self._secret_key)
            self._ready_to_send.set()

            _logger.debug("Session secret key received")

    async def close(self) -> None:
        """Close this connection and all subsequent tasks, websockets, and packet transports.

        Warning
        -------
        - This method should only be called internally.
        - Calling this method may cause issues.
        """
        self._running = False

        await self.stop()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()

            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                ...

            self._heartbeat_task = None

        if self._websocket and not self._websocket.closed:
            await self._websocket.close()
            self._websocket = None

        if self._transport:
            self._transport.close()
            self._transport = None

    async def connect(self, endpoint: str, session_id: str, token: str) -> None:
        """
        Connect to an endpoint with a session ID and token.

        Warning
        -------
        - This method should only be called internally.
        - Calling this method may cause issues.
        """
        self._endpoint = endpoint
        self._session_id = session_id
        self._token = token

        self._running = True

        await self._websocket_handler()

    async def play(self, source: AudioSource) -> None:
        """
        Play audio from a given source.
        
        Warning
        -------
        This method should only be called internally.
        
        Parameters
        ----------
        source : AudioSource
            The source in which the audio will be framed.
        """
        await self._ready_to_send.wait()
        await self._set_speaking(True)

        self._player = AudioPlayer(self)

        try:
            await self._player.play(source)
            await self._player.play(SilentAudioSource(), False)
        except AttributeError:
            pass

        await self.stop()

    async def stop(self) -> None:
        """
        Stop the connection from playing audio.

        Warning
        -------
        This method should only be called internally.
        """
        if not self._player:
            return

        await self._player.stop()
        await self._set_speaking(False)

        self._player = None

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from hikariwave.audio.player import AudioPlayer
from hikariwave.config import Config
from hikariwave.internal.constants import (
    Constants,
    Opcode,
)
from hikariwave.internal.encrypt import Encrypt
from hikariwave.internal.helpers import verify_type
from hikariwave.internal.signal import (
    DisconnectSignal,
    ReconnectSignal,
    ResumeSignal,
)
from hikariwave.networking.gateway import (
    GatewayReadyPayload,
    GatewayReport,
    GatewaySessionDescriptionPayload,
    VoiceGateway,
)
from hikariwave.networking.server import VoiceServer
from typing import TYPE_CHECKING

import asyncio
import hikari
import logging

if TYPE_CHECKING:
    from hikariwave.client import VoiceClient

__all__ = ("VoiceConnection",)

logger: logging.Logger = logging.getLogger("hikari-wave.connection")

class ConnectionState(IntEnum):
    """The voice connection's state."""

    CONNECTED     = 0
    """Voice connection has established it's voice gateway and voice server connections."""
    CONNECTING    = 1
    """Voice connection is pending connections with the voice gateway and voice server."""
    DISCONNECTED  = 2
    """Voice connection is not connected to any voice gateway or voice server."""
    DISCONNECTING = 3
    """Voice connection is pending disconnect with the voice gateway and voice server."""

class VoiceConnection:
    """An active connection to a voice channel."""

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
            The controlling voice system client managing this connection.
        guild_id : hikari.Snowflake
            The ID of the guild this connection manages.
        channel_id : hikari.Snowflake
            The ID of the voice channel this connection manages.
        endpoint : str
            The voice gateway websocket URI.
        session_id : str
            The voice gateway session ID.
        token : str
            The voice gateway token.
        """

        self._client: VoiceClient = client
        self._guild_id: hikari.Snowflake = guild_id
        self._channel_id: hikari.Snowflake = channel_id
        self._endpoint: str = endpoint
        self._session_id: str = session_id
        self._token: str = token
        self._config: Config = self._client._config

        self._ready: asyncio.Event = asyncio.Event()
        self._server: VoiceServer = VoiceServer(self)
        self._gateway: VoiceGateway = VoiceGateway(self)
        self._gateway.set_callback(Opcode.READY, self.__gateway_ready)
        self._gateway.set_callback(Opcode.SESSION_DESCRIPTION, self.__gateway_session_description)

        self._lock: asyncio.Lock = asyncio.Lock()
        self._state: ConnectionState = ConnectionState.DISCONNECTED

        self._reports: asyncio.Queue[GatewayReport] = asyncio.Queue()
        self._report_task: asyncio.Task[None] = None

        self._ssrc: int = None
        self._encryption_mode: Callable[[bytes, int, bytes, bytes], bytes] = None
        self._decryption_mode: Callable[[bytes, bytes], bytes] = None
        self._secret: bytes = None

        self._player: AudioPlayer = AudioPlayer(self)

    async def __gateway_disconnect(self) -> None:
        logger.warning("Voice gateway requested disconnect")

        async with self._lock:
            if self._state not in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
                return

            self._state = ConnectionState.DISCONNECTING

            try:
                if self._server:
                    await self._server.disconnect()

                if self._gateway:
                    await self._gateway.disconnect()
            finally:
                self._state = ConnectionState.DISCONNECTED

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

    async def __gateway_reconnect(self) -> None:
        logger.warning("Voice gateway requested reconnect")

        async with self._lock:
            if self._state != ConnectionState.CONNECTED:
                return

            self._state = ConnectionState.CONNECTING

            try:
                await self._gateway.disconnect()
                await self._gateway.connect(f"{self._endpoint}/v?={Constants.GATEWAY_VERSION}")
                await self._ready.wait()

                self._state = ConnectionState.CONNECTED
                logger.info("Voice gateway reconnect successful")
            except Exception:
                logger.exception("Voice gateway reconnect failed, tearing down...")
                await self.__gateway_disconnect()

    async def __gateway_resume(self) -> None:
        logger.info("Voice gateway requested resume")

        async with self._lock:
            if self._state != ConnectionState.CONNECTED:
                return

            self._state = ConnectionState.CONNECTING

            try:
                await self._gateway._websocket.send_json({
                    "op": Opcode.RESUME,
                    'd': {
                        "server_id": str(self._guild_id),
                        "session_id": self._session_id,
                        "token": self._token,
                        "seq_ack": self._gateway._sequence,
                    }
                })
                await self._ready.wait()

                self._state = ConnectionState.CONNECTED
                logger.info("Voice gateway resume successful")
            except Exception:
                logger.exception("Voice resume failed, attempting reconnect...")
                await self.__gateway_disconnect()

    async def __gateway_session_description(self, payload: GatewaySessionDescriptionPayload) -> None:
        self._encryption_mode = getattr(Encrypt, f"encrypt_{payload.mode}")
        self._decryption_mode = getattr(Encrypt, f"decrypt_{payload.mode}")
        self._secret = payload.secret

        self._ready.set()

    async def __loop_reports(self) -> None:
        try:
            while True:
                report: GatewayReport = await self._reports.get()

                if isinstance(report, DisconnectSignal):
                    await self.__gateway_disconnect()
                elif isinstance(report, ReconnectSignal):
                    await self.__gateway_reconnect()
                elif isinstance(report, ResumeSignal):
                    await self.__gateway_resume()
        except asyncio.CancelledError:
            return

    async def _connect(self) -> None:
        async with self._lock:
            if self._state != ConnectionState.DISCONNECTED:
                return

            self._ready.clear()
            self._state = ConnectionState.CONNECTING

            self._report_task = self._client._tasks.create(self.__loop_reports(), name="connection-reports")

            try:
                await self._gateway.connect(f"{self._endpoint}/?v={Constants.GATEWAY_VERSION}")
                await self._ready.wait()

                self._state = ConnectionState.CONNECTED
            except Exception:
                self._state = ConnectionState.DISCONNECTED
                logging.exception("Exception occurred while connecting to gateway")
                raise

    async def _disconnect(self) -> None:
        async with self._lock:
            if self._state not in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
                return

            self._state = ConnectionState.DISCONNECTING

            if self._server:
                await self._server.disconnect()

            if self._gateway:
                await self._gateway.disconnect()

            if self._report_task:
                self._report_task.cancel()
                await self._report_task

            self._state = ConnectionState.DISCONNECTED

    @property
    def channel_id(self) -> hikari.Snowflake:
        """The ID of the voice channel this connection manages."""
        return self._channel_id

    @property
    def client(self) -> VoiceClient:
        """The controlling voice system client managing this connection."""
        return self._client

    async def disconnect(self) -> None:
        """
        Disconnect from the current channel.
        """

        await self._client.disconnect(self._guild_id)

    @property
    def guild_id(self) -> hikari.Snowflake:
        """The ID of the guild this connection manages."""
        return self._guild_id

    @property
    def latency(self) -> float | None:
        """The heartbeat latency of the voice gateway connection, if connected."""

        if not self._gateway._heartbeat_ack:
            return None

        return self._gateway._heartbeat_ack - self._gateway._heartbeat_sent

    @property
    def player(self) -> AudioPlayer:
        """The audio player responsible for managing all audio playback."""
        return self._player

    def set_config(self, config: Config) -> None:
        """
        Set this specific connection's configuration.

        Parameters
        ----------
        config : Config
            This connection's configuration.

        Raises
        ------
        TypeError
            If the provided config isn't `Config`.
        """

        verify_type(config, Config, "config")
        self._config = config

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import IntEnum
from hikariwave.event.events.voice import VoiceReconnectEvent
from hikariwave.internal.constants import (
    Constants,
    Opcode,
    SpeakingFlag,
)
from hikariwave.internal.dave import DAVEManager
from hikariwave.internal.dev import log_exception
from hikariwave.internal.error import GatewayError
from hikariwave.internal.signal import (
    DisconnectSignal,
    ReconnectSignal,
    ResumeSignal,
)
from hikariwave.internal.websocket import Websocket, WebsocketPacket, WebsocketPacketBytes, WebsocketPacketJSON
from typing import Any, TYPE_CHECKING

import asyncio
import hikari
import logging
import time

if TYPE_CHECKING:
    from hikariwave.connection import VoiceConnection

__all__ = ()

logger: logging.Logger = logging.getLogger("hikari-wave.gateway")

class GatewayPayload:
    """Base payload implementation."""

@dataclass(frozen=True, slots=True)
class GatewayReadyPayload(GatewayPayload):
    """Voice gateway `READY` operation payload."""

    ip: str
    """The Discord voice server IP address to connect to."""
    modes: list[str]
    """All acceptable encryption modes that Discord's voice server supports."""
    port: int
    """The Discord voice server port to connect to."""
    ssrc: int
    """The voice SSRC assigned by Discord for voice packets."""

@dataclass(frozen=True, slots=True)
class GatewayReport:
    """A connection report from the voice gateway."""

    signal: DisconnectSignal | ReconnectSignal | ResumeSignal
    """The signal raised by the voice gateway."""

@dataclass(frozen=True, slots=True)
class GatewaySessionDescriptionPayload(GatewayPayload):
    """Voice gateway `SESSION_DESCRIPTION` payload."""

    dave_protocol_version: int
    """The initial `DAVE` protocol version the Discord voice server will use."""
    mode: str
    """The encryption mode that audio packets should be encrypted with."""
    secret: bytes
    """The secret key used to encrypt/decrypt audio packets."""

class GatewayState(IntEnum):
    """Current state of a voice gateway."""

    CONNECTED     = 0
    """Voice gateway is connected."""
    CONNECTING    = 1
    """Voice gateway is connecting."""
    DISCONNECTED  = 2
    """Voice gateway is not connected."""
    DISCONNECTING = 3
    """Voice gateway is disconnecting."""

class VoiceGateway:
    """Discord voice gateway connection manager."""

    __slots__ = (
        "_connection", "_state",
        "_guild_id", "_channel_id", "_bot_id",
        "_session_id", "_token", "_sequence", "_ssrc",
        "_websocket", "_dave",
        "_task_heartbeat", "_task_listen", "_callbacks",
        "_heartbeat_sent", "_heartbeat_ack",
    )

    def __init__(self, connection: VoiceConnection) -> None:
        """
        Create a Discord voice gateway connection manager.

        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        """

        self._connection: VoiceConnection = connection
        self._state: GatewayState = GatewayState.DISCONNECTED

        self._sequence: int = -1
        self._ssrc: int | None = None

        self._websocket: Websocket = Websocket()
        self._dave: DAVEManager = DAVEManager(self)

        self._task_heartbeat: asyncio.Task[None] | None = None
        self._task_listen: asyncio.Task[None] | None = None
        self._callbacks: dict[Opcode, Callable[[GatewayPayload], Coroutine[Any, Any, None]]] = {}

        self._heartbeat_sent: float = 0.0
        self._heartbeat_ack: float = 0.0

    async def __callback(self, opcode: Opcode, payload: GatewayPayload) -> None:
        if opcode not in self._callbacks:
            return

        await self._callbacks[opcode](payload)

    async def __loop_heartbeat(self, interval: float) -> None:
        while self._state in (GatewayState.CONNECTED, GatewayState.CONNECTING):
            try:
                now: float = time.time()

                if self._heartbeat_ack > 0 and now - self._heartbeat_ack > interval * 2:
                    logger.warning("Voice gateway heartbeat ACK timed out")
                    raise ReconnectSignal()

                await self._websocket.send_json({
                    "op": Opcode.HEARTBEAT,
                    'd': {
                        't': int(now),
                        "seq_ack": self._sequence,
                    }
                })
                self._heartbeat_sent = now

                await asyncio.sleep(interval)
            except asyncio.CancelledError as e:
                log_exception(e)
                return
            except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
                log_exception(e)
                await self.__signal(e)
                return

    async def __loop_listen(self) -> None:
        try:
            while True:
                packet: WebsocketPacket = await self._websocket.receive()

                if isinstance(packet, WebsocketPacketJSON):
                    opcode: int = packet.payload.get("op")
                    if opcode is None:
                        continue

                    self._sequence = packet.payload.get("seq", self._sequence)
                    payload_json: dict[str, Any] = packet.payload.get('d', {})

                    match opcode:
                        case Opcode.READY:
                            self._ssrc = payload_json.get("ssrc")
                            await self.__callback(Opcode.READY, GatewayReadyPayload(
                                payload_json.get("ip"), payload_json.get("modes"), payload_json.get("port"), self._ssrc,
                            ))
                        case Opcode.SESSION_DESCRIPTION:
                            dave_version: int = payload_json.get("dave_protocol_version", 0)
                            if dave_version > 0:
                                await self._dave.initialize_session(dave_version)

                            await self.__callback(Opcode.SESSION_DESCRIPTION, GatewaySessionDescriptionPayload(
                                dave_version, payload_json.get("mode"), bytes(payload_json.get("secret_key")),
                            ))
                        case Opcode.SPEAKING:
                            user_id: hikari.Snowflake = hikari.Snowflake(payload_json.get("user_id"))
                            ssrc: int = payload_json.get("ssrc")

                            self._connection._client._cache.set_member_ssrc(user_id, ssrc)
                        case Opcode.HEARTBEAT_ACK:
                            self._heartbeat_ack = time.time()
                        case Opcode.RESUMED:
                            self._state = GatewayState.CONNECTED

                            logger.debug(f"Voice gateway session resumed: Session={self._connection._session_id}, Token={self._connection._token}")

                            self._connection._client._event_factory.emit(
                                VoiceReconnectEvent,
                                channel_id=self._connection._channel_id,
                                guild_id=self._connection._guild_id,
                            )
                        case Opcode.CLIENTS_CONNECT:...
                        case Opcode.CLIENT_DISCONNECT:...
                        case Opcode.DAVE_PREPARE_TRANSITION:
                            await self._dave.handle_prepare_transition(
                                payload_json.get("transition_id"),
                                payload_json.get("protocol_version"),
                            )
                        case Opcode.DAVE_EXECUTE_TRANSITION:
                            await self._dave.handle_execute_transition(payload_json.get("transition_id"))
                        case Opcode.DAVE_PREPARE_EPOCH:
                            await self._dave.handle_prepare_epoch(
                                payload_json.get("transition_id"),
                                payload_json.get("epoch"),
                            )
                        case _:
                            logger.debug(f"Received undocumented voice gateway operation: `{opcode}`")
                            logger.debug(packet.payload)
                elif isinstance(packet, WebsocketPacketBytes):
                    self._sequence, opcode, payload_bytes = DAVEManager.parse_frame(packet.payload)

                    match opcode:
                        case Opcode.DAVE_MLS_EXTERNAL_SENDER:
                            await self._dave.set_external_sender(payload_bytes)
                        case Opcode.DAVE_MLS_PROPOSALS:
                            await self._dave.handle_proposals(
                                payload_bytes,
                                [int(id) for id in self._connection._client._cache.get_channel_member_ids(self._connection._channel_id)],
                            )
                        case Opcode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION:
                            await self._dave.handle_commit(payload_bytes)
                        case Opcode.DAVE_MLS_WELCOME:
                            await self._dave.handle_welcome(payload_bytes)
                        case _:
                            logger.debug(f"Received undocumented DAVE voice gateway operation: `{opcode}`")
                            logger.debug(packet.payload)
        except asyncio.CancelledError as e:
            log_exception(e)
            return
        except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
            log_exception(e)
            await self.__signal(e)
            return

    async def __signal(self, signal: DisconnectSignal | ReconnectSignal | ResumeSignal) -> None:
        await self._connection._reports.put(GatewayReport(signal))

    async def connect(self, url: str) -> None:
        """
        Connect to a Discord voice gateway endpoint.

        Parameters
        ----------
        url : str
            The websocket URL to Discord's voice gateway.
        """

        if self._state in (GatewayState.CONNECTED, GatewayState.CONNECTING):
            return

        self._state = GatewayState.CONNECTING

        logger.debug(f"Connecting to voice gateway: {url}")

        try:
            await self._websocket.connect(url)
        except ReconnectSignal as e:
            log_exception(e)
            await self.__signal(e)
            return

        try:
            packet: WebsocketPacketBytes | WebsocketPacketJSON = await self._websocket.receive()

            if not isinstance(packet, WebsocketPacketJSON):
                error: str = "Expecting a JSON-encoded HELLO packet, not `bytes`"
                raise GatewayError(error)
        except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
            log_exception(e)
            await self.__signal(e)
            return

        opcode: int = packet.payload.get("op")

        if opcode != Opcode.HELLO:
            error: str = f"Expected `HELLO` ({Opcode.HELLO.value}) payload, not `{Opcode(opcode).name}` (`{opcode}`)"
            raise GatewayError(error)

        payload: dict[str, Any] = packet.payload.get('d', {})
        heartbeat_interval: float = payload.get("heartbeat_interval", 0.0) / 1000

        self._task_heartbeat = self._connection._client._tasks.create(self.__loop_heartbeat(heartbeat_interval), name="gateway-heartbeat")

        try:
            await self._websocket.send_json({
                "op": Opcode.IDENTIFY,
                'd': {
                    "server_id": str(self._connection._guild_id),
                    "user_id": str(self._connection._client._bot_id),
                    "session_id": self._connection._session_id,
                    "token": self._connection._token,
                    "max_dave_protocol_version": Constants.DAVE_VERSION,
                },
            })
        except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
            log_exception(e)
            await self.__signal(e)
            return

        logger.debug(
            f"Identified with voice gateway: Server={self._connection._guild_id}, Session={self._connection._session_id}, Token={self._connection._token}, DAVE={Constants.DAVE_VERSION}"
        )

        self._task_listen = self._connection._client._tasks.create(self.__loop_listen(), name="gateway-listener")
        self._state = GatewayState.CONNECTED

    async def disconnect(self) -> None:
        """
        Disconnect from Discord's voice gateway.
        """

        if self._state in (GatewayState.DISCONNECTED, GatewayState.DISCONNECTING):
            return

        self._state = GatewayState.DISCONNECTING

        logger.debug("Disconnecting from voice gateway")

        tasks: tuple[asyncio.Task[None]] = tuple(task for task in (self._task_heartbeat, self._task_listen) if task and not task.done())

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await self._websocket.disconnect()

        self._sequence = -1

        self._task_heartbeat = None
        self._task_listen = None

        self._heartbeat_sent = 0.0
        self._heartbeat_ack = 0.0

        self._state = GatewayState.DISCONNECTED

    async def select_protocol(self, ip: str, port: int, mode: str) -> None:
        """
        Send the `SELECT_PROTOCOL` operation payload to Discord's voice gateway.

        Parameters
        ----------
        ip : str
            This device's IPv4 address.
        port : int
            The port for Discord's voice server to communicate with this device.
        mode : str
            The desired encryption method to use with Discord's voice server.
        """

        try:
            await self._websocket.send_json({
                "op": Opcode.SELECT_PROTOCOL,
                'd': {
                    "protocol": "udp",
                    "data": {
                        "address": ip,
                        "port": port,
                        "mode": mode,
                    }
                }
            })
        except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
            log_exception(e)
            await self.__signal(e)
            return

        logger.debug(f"Voice protocol selected: Address={ip}:{port}, Mode={mode}")

    def set_callback(self, opcode: Opcode, callback: Callable[[GatewayPayload], Coroutine[Any, Any, None]]) -> None:
        """
        Set a callback method for the arrival of a specific voice gateway operation code.

        Parameters
        ----------
        opcode : Opcode
            The voice gateway operation code to listen for.
        callback : Callable[[GatewayPayload], Coroutine[Any, Any, None]]
            The asynchronous method to call as the callback with the payload of this operation.
        """

        self._callbacks[opcode] = callback

    async def set_speaking(self, state: bool, priority: bool = False) -> None:
        """
        Set our `SPEAKING` state.

        Parameters
        ----------
        state : bool
            If we are speaking.
        priority : bool
            If we should speak with `PRIORITY` status.
        """

        flags: int = 0

        if state:
            flags |= SpeakingFlag.VOICE

        if priority:
            flags |= SpeakingFlag.PRIORITY

        try:
            await self._websocket.send_json({
                "op": Opcode.SPEAKING,
                'd': {
                    "speaking": flags,
                    "delay": 0,
                    "ssrc": self._ssrc,
                }
            })
        except (DisconnectSignal, ReconnectSignal, ResumeSignal) as e:
            log_exception(e)
            await self.__signal(e)
            return

        logger.debug(f"Set speaking state to {state}")

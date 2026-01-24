from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from hikariwave.event.events.voice import VoiceReconnectEvent
from hikariwave.internal.constants import (
    Constants,
    Opcode,
    SpeakingFlag,
)
from hikariwave.internal.dave import DAVEManager
from hikariwave.internal.error import GatewayError
from hikariwave.internal.signal import (
    DisconnectSignal,
    ReconnectSignal,
    ResumeSignal,
)
from hikariwave.internal.websocket import Websocket, WebsocketPacket, WebsocketPacketBytes, WebsocketPacketJSON
from typing import Any, Callable, Coroutine, TYPE_CHECKING

import asyncio
import hikari
import logging
import random
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
    RESUMING      = 4
    """Voice gateway is resuming."""

class VoiceGateway:
    """Discord voice gateway connection manager."""

    __slots__ = (
        "_connection", "_state",
        "_guild_id", "_channel_id", "_bot_id",
        "_session_id", "_token", "_sequence", "_ssrc",
        "_gateway_url", "_websocket", "_dave",
        "_task_heartbeat", "_task_listen", "_callbacks",
        "_heartbeat_sent", "_heartbeat_ack",
        "_reconnect_attempts", "_task_reconnect",
    )

    def __init__(
        self,
        connection: VoiceConnection,
        guild_id: hikari.Snowflake,
        channel_id: hikari.Snowflake,
        bot_id: hikari.Snowflake,
        session_id: str,
        token: str,
    ) -> None:
        """
        Create a Discord voice gateway connection manager.
        
        Parameters
        ----------
        connection : VoiceConnection
            The active voice connection.
        guild_id : hikari.Snowflake
            The ID of the guild the connection is in.
        channel_id : hikari.Snowflake
            The ID of the channel the connection is in.
        bot_id : hikari.Snowflake
            The ID of the Discord OAuth2 application controlling the connection.
        session_id : str
            The session ID provided by Discord's gateway.
        token : str
            The token provided by Discord's gateway.
        """
        
        self._connection: VoiceConnection = connection
        self._state: GatewayState = GatewayState.DISCONNECTED
        
        self._guild_id: hikari.Snowflake = guild_id
        self._channel_id: hikari.Snowflake = channel_id
        self._bot_id: hikari.Snowflake = bot_id

        self._session_id: str = session_id
        self._token: str = token
        self._sequence: int = -1
        self._ssrc: int | None = None

        self._gateway_url: str | None = None
        self._websocket: Websocket = Websocket()
        self._dave: DAVEManager = DAVEManager(self)
        
        self._task_heartbeat: asyncio.Task[None] | None = None
        self._task_listen: asyncio.Task[None] | None = None
        self._callbacks: dict[Opcode, Callable[[GatewayPayload], Coroutine[Any, Any, None]]] = {}

        self._heartbeat_sent: float = 0.0
        self._heartbeat_ack: float = 0.0

        self._reconnect_attempts: int = 0
        self._task_reconnect: asyncio.Task[None] | None = None
    
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
            except asyncio.CancelledError:
                return
            except DisconnectSignal:
                logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
                await self.disconnect()
                return
            except ReconnectSignal:
                await self.__reconnect()
                return
            except ResumeSignal:
                await self.__resume()
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
                                self._dave.initialize_session(dave_version)

                            await self.__callback(Opcode.SESSION_DESCRIPTION, GatewaySessionDescriptionPayload(
                                dave_version, payload_json.get("mode"), bytes(payload_json.get("secret_key")),
                            ))
                        case Opcode.SPEAKING:
                            user_id: hikari.Snowflake = hikari.Snowflake(payload_json.get("user_id"))
                            ssrc: int = payload_json.get("ssrc")

                            self._connection._client._ssrcs[user_id] = ssrc
                            self._connection._client._ssrcsr[ssrc] = user_id
                        case Opcode.HEARTBEAT_ACK:
                            self._heartbeat_ack = time.time()
                        case Opcode.RESUMED:
                            self._state = GatewayState.CONNECTED
                            self._reconnect_attempts = 0

                            logger.debug(f"Voice gateway session resumed: Session={self._session_id}, Token={self._token}")

                            self._connection._client._event_factory.emit(
                                VoiceReconnectEvent,
                                channel_id=self._channel_id,
                                guild_id=self._guild_id,
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
                                [int(id) for id in self._connection._client._channels[self._channel_id].members.keys()],
                            )
                        case Opcode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION:
                            await self._dave.handle_commit(payload_bytes)
                        case Opcode.DAVE_MLS_WELCOME:
                            await self._dave.handle_welcome(payload_bytes)
                        case _:
                            logger.debug(f"Received undocumented DAVE voice gateway operation: `{opcode}`")
                            logger.debug(packet.payload)
        except asyncio.CancelledError:
            return
        except DisconnectSignal:
            logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
            await self.disconnect()
            return
        except ReconnectSignal:
            await self.__reconnect()
            return
        except ResumeSignal:
            await self.__resume()
            return

    async def __reconnect(self) -> None:
        if self._state is GatewayState.CONNECTING:
            return
        
        if self._task_reconnect and not self._task_reconnect.done():
            return
        
        logger.debug(f"Voice gateway signalled to reconnect; reconnecting...")

        async def reconnect() -> None:
            self._reconnect_attempts += 1
            
            base: float = 1.0
            cap: float = 60.0
            
            delay: float = min(cap, base * (2 ** self._reconnect_attempts))
            jitter: float = delay * 0.25
            delay += jitter * (2 * random.random() - 1)

            logger.debug(f"Voice gateway reconnect attempt {self._reconnect_attempts} in {delay:.2f}s")

            await asyncio.sleep(delay)

            await self.disconnect()
            await self.connect(self._gateway_url)
        
        self._task_reconnect = asyncio.create_task(reconnect())

    async def __resume(self) -> None:
        self._state = GatewayState.RESUMING

        logger.debug(f"Voice gateway signalled to resume; resuming...")

        try:
            await self._websocket.send_json({
                "op": Opcode.RESUME,
                'd': {
                    "server_id": str(self._guild_id),
                    "session_id": self._session_id,
                    "token": self._token,
                    "seq_ack": self._sequence,
                }
            })
        except DisconnectSignal:
            logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
            await self.disconnect()
            return
        except ReconnectSignal:
            await self.__reconnect()
            return
        except ResumeSignal:
            await self.__resume()
            return

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

        logger.debug(f"Connecting to Discord voice gateway: {url}")
        self._gateway_url = url

        try:
            await self._websocket.connect(url)
        except ReconnectSignal:
            await self.__reconnect()
            return
        
        try:
            packet: WebsocketPacketBytes | WebsocketPacketJSON = await self._websocket.receive()

            if not isinstance(packet, WebsocketPacketJSON):
                error: str = "Expecting a JSON-encoded packet, not `bytes`"
                raise GatewayError(error)
        except DisconnectSignal:
            logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
            await self.disconnect()
            return
        except ReconnectSignal:
            await self.__reconnect()
            return
        except ResumeSignal:
            await self.__resume()
            return
        
        opcode: int = packet.payload.get("op")
        
        if opcode != Opcode.HELLO:
            error: str = f"Expected `HELLO` ({Opcode.HELLO.value}) payload, not `{Opcode(opcode).name}` (`{opcode}`)"
            raise GatewayError(error)
        
        payload: dict[str, Any] = packet.payload.get('d', {})
        heartbeat_interval: float = payload.get("heartbeat_interval", 0.0) / 1000

        self._task_heartbeat = asyncio.create_task(self.__loop_heartbeat(heartbeat_interval))

        try:
            await self._websocket.send_json({
                "op": Opcode.IDENTIFY,
                'd': {
                    "server_id": str(self._guild_id),
                    "user_id": str(self._bot_id),
                    "session_id": self._session_id,
                    "token": self._token,
                    "max_dave_protocol_version": Constants.DAVE_VERSION,
                },
            })
        except DisconnectSignal:
            logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
            await self.disconnect()
            return
        except ReconnectSignal:
            await self.__reconnect()
            return
        except ResumeSignal:
            await self.__resume()
            return
        
        logger.debug(f"Identified with voice gateway: Server={self._guild_id}, Session={self._session_id}, Token={self._token}, DAVE={Constants.DAVE_VERSION}")

        self._task_listen = asyncio.create_task(self.__loop_listen())
        self._reconnect_attempts = 0
    
    async def disconnect(self) -> None:
        """
        Disconnect from Discord's voice gateway.
        """

        if self._state in (GatewayState.DISCONNECTED, GatewayState.DISCONNECTING):
            return
        
        self._state = GatewayState.DISCONNECTING

        logger.debug(f"Disconnecting from Discord voice gateway: {self._gateway_url}")

        if self._task_heartbeat:
            self._task_heartbeat.cancel()

        if self._task_listen:
            self._task_listen.cancel()
        
        await asyncio.gather(*(task for task in (self._task_heartbeat, self._task_listen) if task), return_exceptions=True)
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
        except DisconnectSignal:
            logger.debug(f"Voice gateway signalled to disconnect; disconnecting...")
            await self.disconnect()
            return
        except ReconnectSignal:
            await self.__reconnect()
            return
        except ResumeSignal:
            await self.__resume()
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
        except (DisconnectSignal, ReconnectSignal, ResumeSignal):
            return
        
        logger.debug(f"Set speaking state to {state}")
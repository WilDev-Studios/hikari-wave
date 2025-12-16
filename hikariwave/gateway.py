from __future__ import annotations

from dataclasses import dataclass
from hikariwave.constants import CloseCode, Opcode
from hikariwave.error import GatewayError
from hikariwave.event.types import WaveEventType
from typing import Any, Callable, Coroutine, Final, Sequence, TYPE_CHECKING

import asyncio
import hikari
import json
import logging
import time
import websockets

if TYPE_CHECKING:
    from .connection import VoiceConnection

__all__: Final[Sequence[str]] = ("VoiceGateway",)

logger: logging.Logger = logging.getLogger("hikari-wave.gateway")

class Payload:
    """Base payload implementation."""

@dataclass
class ReadyPayload(Payload):
    """READY gateway payload."""

    ssrc: int
    """Our assigned SSRC."""
    ip: str
    """Discord's voice server IP."""
    port: int
    """Discord's voice server port."""
    modes: list[str]
    """All acceptable encryption modes that Discord's voice server supports."""

@dataclass
class SessionDescriptionPayload(Payload):
    """SESSION_DESCRIPTION gateway payload."""

    mode: str
    """The encryption mode the player should use when sending audio."""
    secret: bytes
    """Our secret key that should be used in encryption."""

class VoiceGateway:
    """The background communication system with Discord's voice gateway."""

    def __init__(
        self,
        connection: VoiceConnection,
        guild_id: hikari.Snowflakeish,
        channel_id: hikari.Snowflakeish,
        bot_id: hikari.Snowflakeish,
        session_id: str,
        token: str,
    ) -> None:
        """
        Create a new Discord voice gateway communication system.
        
        Parameters
        ----------
        connection : VoiceConnection
            The current voice connection to a guild/channel.
        guild_id : hikari.Snowflakeish
            The ID of the guild the channel is in.
        channel_id : hikari.Snowflakeish
            The ID of the channel we are connected to.
        bot_id : hikari.Snowflakeish
            The ID of the bot user connected.
        session_id : str
            Our unique session ID provided by Discord's OAuth2 gateway.
        token : str
            Our unique token provided by Discord's OAuth2 gateway.
        """
        
        self.connection: VoiceConnection = connection
        self.guild_id: hikari.Snowflakeish = guild_id
        self.channel_id: hikari.Snowflakeish = channel_id
        self.bot_id: hikari.Snowflakeish = bot_id

        self.session_id: str = session_id
        self.token: str = token
        self.sequence: int = -1
        self.ssrc: int = None

        self.gateway: str = None
        self.websocket: websockets.ClientConnection = None
        self.callbacks: dict[Opcode, Callable[[Payload], Coroutine[Any, Any, None]]] = {}

        self.task_heartbeat: asyncio.Task = None
        self.task_listener: asyncio.Task = None

        self.last_heartbeat_sent: float = 0.0
        self.last_heartbeat_ack: float = 0.0

    async def _call_callback(self, opcode: Opcode, payload: Payload) -> None:
        await self.callbacks[opcode](payload)

    async def _heartbeat(self) -> None:
        t: int = int(time.time())
        seq_ack: int = self.sequence

        await self._send_packet({
            "op": Opcode.HEARTBEAT,
            'd': {
                't': t,
                "seq_ack": seq_ack,
            }
        })
        logger.debug(f"Heartbeat: T={t}, SeqAck={seq_ack}")

    async def _loop_heartbeat(self, interval: float) -> None:
        while True:
            await self._heartbeat()
            self.last_heartbeat_sent = time.time()

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return

    async def _loop_listen(self) -> None:
        while True:
            packet: dict[str, Any] = await self._recv_packet()
            opcode: int = packet.get("op")
            data: dict[str, Any] = packet.get('d', {})

            self.sequence = packet.get("seq", self.sequence)

            match opcode:
                case Opcode.READY:
                    self.ssrc = data["ssrc"]
                    await self._call_callback(Opcode.READY, ReadyPayload(
                        data["ssrc"], data["ip"], data["port"], data["modes"],
                    ))
                case Opcode.SESSION_DESCRIPTION:
                    await self._call_callback(Opcode.SESSION_DESCRIPTION, SessionDescriptionPayload(
                        data["mode"], bytes(data["secret_key"]),
                    ))
                case Opcode.SPEAKING:
                    user_id: int = int(data["user_id"])
                    ssrc: int = data["ssrc"]

                    self.connection.client.ssrcs[user_id] = ssrc
                    self.connection.client.ssrcs_reference[ssrc] = user_id
                case Opcode.HEARTBEAT_ACK:
                    self.last_heartbeat_ack = time.time()
                case Opcode.RESUMED:
                    logger.info(f"Client session resumed after disconnect")

                    self.connection.client.event_factory.emit(
                        WaveEventType.VOICE_RECONNECT,
                        self.channel_id,
                        self.guild_id,
                    )
                case Opcode.CLIENTS_CONNECT:...
                case Opcode.CLIENT_DISCONNECT:...
                case Opcode.UNDOCUMENTED_15:...
                case Opcode.UNDOCUMENTED_18:...
                case Opcode.UNDOCUMENTED_20:...
                case None: return
                case _:
                    logger.warning(f"Unhandled opcode {opcode}! Please alert hikari-wave's developers ASAP")
                    logger.warning(packet)

    async def _identify(self) -> None:
        await self._send_packet({
            "op": Opcode.IDENTIFY,
            'd': {
                "server_id": str(self.guild_id),
                "user_id": str(self.bot_id),
                "session_id": self.session_id,
                "token": self.token,
            },
        })
        logger.debug(
            f"Identified with gateway: Server={self.guild_id}, User={self.bot_id}, Session={self.session_id}, Token={self.token}"
        )

    async def _recv_packet(self) -> dict[str, Any]:
        try:
            packet: dict[str, Any] = json.loads(await self.websocket.recv())
            return packet
        except json.JSONDecodeError as e:
            await self.disconnect()

            error: str = f"Couldn't decode websocket packet: {e}\n{packet}"
            raise GatewayError(error)
        except websockets.ConnectionClosed as e:
            await self.disconnect()

            logger.debug(f"Websocket connection was closed")

            match e.code:
                case CloseCode.SESSION_NO_LONGER_VALID | CloseCode.SESSION_TIMEOUT:
                    await self.connection._gateway_reconnect()
                    return {}
                case CloseCode.VOICE_SERVER_CRASHED:
                    await self._resume()
                case _:
                    return {}

    async def _resume(self) -> None:
        await self._send_packet({
            "op": Opcode.RESUME,
            'd': {
                "server_id": str(self.guild_id),
                "session_id": self.session_id,
                "token": self.token,
                "seq_ack": self.sequence,
            }
        })

    async def _send_packet(self, data: dict[str, Any]) -> None:
        try:
            await self.websocket.send(json.dumps(data))
        finally:
            return
        
    async def _wait_hello(self) -> float:
        packet: dict[str, Any] = await self._recv_packet()
        opcode: int = packet.get("op")
        data: dict[str, Any] = packet.get('d', {})

        if opcode != Opcode.HELLO:
            error: str = f"Expected HELLO, not {Opcode(opcode).name}"
            raise GatewayError(error)
        
        return data.get("heartbeat_interval", 0) / 1000

    async def connect(self, gateway_url: str) -> None:
        """
        Connect to Discord's voice gateway.
        
        Parameters
        ----------
        gateway_url : str
            The URL to Discord's voice gateway.
        
        Raises
        ------
        OSError
            If the TCP handshake failed.
        TimeoutError
            If the opening handshake timed out.
        websockets.InvalidHandshake
            If the opening handshake failed.
        """
        
        logger.debug(f"Connecting to gateway: {gateway_url}")
        self.gateway = gateway_url

        try:
            self.websocket = await websockets.connect(self.gateway)
        except OSError as e:
            error: str = f"TCP handshake failed: {e}"
            raise GatewayError(error)
        except TimeoutError as e:
            error: str = f"Opening handshake timed out: {e}"
            raise GatewayError(error)
        except websockets.InvalidHandshake as e:
            error: str = f"Opening handshake failed: {e}"
            raise GatewayError(error)

        heartbeat_interval: float = await self._wait_hello()
        self.task_heartbeat = asyncio.create_task(self._loop_heartbeat(heartbeat_interval))

        await self._identify()

        self.task_listener = asyncio.create_task(self._loop_listen())
    
    async def disconnect(self) -> None:
        """
        Disconnect from Discord's voice gateway.
        """
        
        logger.debug(f"Disconnecting from gateway: {self.gateway}")

        if self.task_listener:
            self.task_listener.cancel()
            self.task_listener = None
        
        if self.task_heartbeat:
            self.task_heartbeat.cancel()
            self.task_heartbeat = None
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        self.sequence = -1
        self.gateway = None

        self.last_heartbeat_ack = 0.0
        self.last_heartbeat_sent = 0.0

    async def select_protocol(self, ip: str, port: int, mode: str) -> None:
        """
        Send the SELECT_PROTOCOL payload to Discord's voice gateway.
        
        Parameters
        ----------
        ip : str
            Our public IPv4 address.
        port : int
            Our address' open port for communication.
        mode : str
            Our desired encryption method to use for audio.
        """
        
        await self._send_packet({
            "op": Opcode.SELECT_PROTOCOL,
            'd': {
                "protocol": "udp",
                "data": {
                    "address": ip,
                    "port": port,
                    "mode": mode,
                },
            },
        })

    def set_callback(self, opcode: Opcode, callback: Callable[[Payload], Coroutine[Any, Any, None]]) -> None:
        """
        Set a payload callback.
        
        Parameters
        ----------
        opcode : Opcode
            The opcode to listen for.
        callback : Callable[[Payload], Coroutine[Any, Any, None]]
            The callback to call when we receive the opcode.
        """
        
        self.callbacks[opcode] = callback

    async def set_speaking(self, state: bool) -> None:
        """
        Set the SPEAKING state of the client.
        
        Parameters
        ----------
        state : bool
            If we are speaking or not.
        """
        
        await self._send_packet({
            "op": Opcode.SPEAKING,
            'd': {
                "speaking": int(state),
                "delay": 0,
                "ssrc": self.ssrc,
            },
        })
        logger.debug(f"Set speaking state to {state}")
from __future__ import annotations

from hikariwave.error import ServerError
from hikariwave.event.types import WaveEventType
from typing import Callable, Final, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import VoiceClient

import asyncio
import hikari
import logging
import struct

__all__: Final[Sequence[str]] = ("VoiceServer",)

logger: logging.Logger = logging.getLogger("hikari-wave.server")

class Protocol(asyncio.DatagramProtocol):
    """Background UDP protocol for communication with Discord's voice servers."""

    def __init__(self, ip_discover_future: asyncio.Future[bytes], rtp_listener: Callable[[int], None]) -> None:
        """
        Create a UDP server protocol.
        
        Parameters
        ----------
        ip_discover_future : asyncio.Future[bytes]
            The future to set when our IP is discovered.
        rtp_listener : Callable[[int], None]
            The callback to call when we receive a non-IP discovery packet.
        """
        
        self._transport: asyncio.DatagramTransport = None

        self._ip_discover_future: asyncio.Future[bytes] = ip_discover_future
        self._rtp_listener: Callable[[int], None] = rtp_listener

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """
        Called automatically when a UDP connection is made.
        
        Parameters
        ----------
        transport : asyncio.DatagramTransport
            The UDP transport.
        """
        
        self._transport = transport

    def datagram_received(self, data: bytes, address: tuple[str, int]) -> None:
        """
        Automatically called when we receive a UDP packet.
        
        Parameters
        ----------
        data : bytes
            The UDP packet data
        address : tuple[str, int]
            The address that sent this packet.
        """

        if not self._ip_discover_future.done():
            self._ip_discover_future.set_result(data)
            return

        self._rtp_listener(data)
    
    def error_received(self, exc: Exception):
        """
        Automatically called when an error occurs.
        
        Parameters
        ----------
        exc : Exception
            The error that occurred.
        """
        
        if self._ip_discover_future.done():
            self._ip_discover_future.set_exception(exc)
            return 

class VoiceServer:
    """The background server responsible for communicating with Discord's voice servers."""

    def __init__(
        self,
        client: VoiceClient,
    ) -> None:
        """
        Create a new voice server connection.
        
        Parameters
        ----------
        client : VoiceClient
            The voice client handling all bot connections and state.
        """
        
        self._client: VoiceClient = client

        self._ip: str = None
        self._port: int = None
        self._ssrc: int = None
        self._udp: asyncio.DatagramTransport = None

        self._last_audio: dict[int, float] = {}
        self._watch_task: asyncio.Task = None

    async def _discover_ip(self) -> tuple[str, int]:
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        future: asyncio.Future[bytes] = loop.create_future()

        self._udp, _ = await loop.create_datagram_endpoint(
            lambda: Protocol(future, self._rtp_packet),
            remote_addr=(self._ip, self._port),
        )

        packet: bytes = struct.pack("!HHI", 0x1, 70, self._ssrc) + bytes(70)
        self._udp.sendto(packet)

        data: bytes = await asyncio.wait_for(future, 3.0)

        if (type_ := struct.unpack("!H", data[0:2])[0]) != 0x0002:
            error: str = f"Expected packet type 2, got {type_}"
            raise ServerError(error)
    
        if (len_ := struct.unpack("!H", data[2:4])[0]) != 70:
            error: str = f"Expected packet length of 70, got {len_}"
            raise ServerError(error)

        external_ip: str = data[8:72].split(b"\x00", 1)[0].decode("ascii")
        external_port: int = struct.unpack("!H", data[72:74])[0]

        logger.debug(f"External address discovered: ({external_ip}:{external_port})")
        return external_ip, external_port

    def _rtp_packet(self, data: bytes) -> None:
        if len(data) < 12: return

        ssrc: int = struct.unpack_from(">I", data, 8)[0]

        if ssrc not in self._client._ssrcs_reference:
            return

        now: float = asyncio.get_running_loop().time()
        is_new: bool = ssrc not in self._last_audio
        self._last_audio[ssrc] = now

        if not is_new:
            return
        
        user_id: hikari.Snowflake = self._client._ssrcs_reference[ssrc]
        member: hikari.Member = self._client._views[user_id]
        channel_id: hikari.Snowflake = self._client._members[member.id].channel_id
        channel = self._client._channels[channel_id]
        guild: hikari.Snowflake = channel.guild_id
        self._client._event_factory.emit(
            WaveEventType.MEMBER_START_SPEAKING,
            channel_id,
            guild,
            member,
        )

        if len(channel.active) == 0:
            self._client._event_factory.emit(
                WaveEventType.VOICE_ACTIVE,
                channel_id,
                guild,
            )
        
        channel.active.add(user_id)

    async def _watch_silence(self) -> None:
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

        try:
            while True:
                now: float = loop.time()

                for ssrc, last in list(self._last_audio.items()):
                    if now - last <= 0.25:
                        continue

                    del self._last_audio[ssrc]

                    user: hikari.Snowflake = self._client._ssrcs_reference[ssrc]
                    member: hikari.Member = self._client._views[user]
                    channel_id: hikari.Snowflake = self._client._members[member.id].channel_id
                    channel = self._client._channels[channel_id]
                    guild: hikari.Snowflake = channel.guild_id

                    channel.active.remove(user)

                    self._client._event_factory.emit(
                        WaveEventType.MEMBER_STOP_SPEAKING,
                        channel,
                        guild,
                        member,
                    )
                
                    if len(channel.active) == 0:
                        self._client._event_factory.emit(
                            WaveEventType.VOICE_INACTIVE,
                            channel_id,
                            guild,
                        )

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def connect(self, ip: str, port: int, ssrc: int) -> tuple[str, int]:
        """
        Connect to a Discord voice server.
        
        Parameters
        ----------
        ip : str
            The Discord voice server's IP.
        port : int
            The Discord voice server's port.
        ssrc : int
            Our assigned SSRC by Discord's voice gateway.
        
        Returns
        -------
        tuple[str, int]
            Our public, discovered IP address.
        """
        
        self._ip, self._port, self._ssrc = ip, port, ssrc

        logger.debug(f"Connecting to voice server: IP={ip}, Port={port}, SSRC={ssrc}")
        local_address: tuple[str, int] = await self._discover_ip()

        self._watch_task = asyncio.create_task(self._watch_silence())

        return local_address

    async def disconnect(self) -> None:
        """
        Disconnect from Discord's voice server.
        """
        
        logger.debug(f"Disconnected from server: IP={self._ip}, Port={self._port}")
        
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        
        self._last_audio.clear()

        if self._udp:
            self._udp.close()
            self._udp = None
    
    async def send(self, data: bytes) -> None:
        """
        Send a UDP packet to Discord's voice server.
        
        Parameters
        ----------
        data : bytes
            The UDP packet to send.
        """
        
        if not self._udp or self._udp.is_closing():
            return
    
        self._udp.sendto(data)
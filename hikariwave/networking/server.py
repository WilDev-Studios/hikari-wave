from __future__ import annotations

from collections.abc import Callable
from hikariwave.internal.constants import Audio
from hikariwave.internal.dev import log_exception
from hikariwave.event.events.member import (
    MemberSpeechEvent,
    MemberStartSpeakingEvent,
    MemberStopSpeakingEvent,
)
from hikariwave.event.events.voice import VoiceWarningEvent
from hikariwave.event.types import VoiceWarningType
from hikariwave.internal.error import ServerError
from typing import TypeAlias, TYPE_CHECKING

if TYPE_CHECKING:
    from hikariwave.client import VoiceChannelMeta, VoiceConnection

import asyncio
import hikari
import logging
import struct

__all__ = ()

SSRC: TypeAlias = int

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

class RTPStats:
    __slots__ = (
        "_prev_arrival",
        "_prev_timestamp",
        "_jitter",
        "_last_seq",
        "_received",
        "_lost",
    )

    def __init__(self) -> None:
        self._prev_arrival: float | None = None
        self._prev_timestamp: int | None = None
        self._jitter: float = 0.0
        self._last_seq: int | None = None
        self._received: int = 0
        self._lost: int = 0

    def update(self, seq: int, timestamp: int, arrival_time: float) -> None:
        if self._last_seq is not None:
            expected: int = (self._last_seq + 1) & Audio.BIT_16U
            if seq != expected:
                delta: int = (seq - expected) & Audio.BIT_16U
                self._lost += delta

        self._last_seq = seq
        self._received += 1

        arrival: float = arrival_time * Audio.SAMPLING_RATE

        if self._prev_arrival is not None:
            delta: float = (arrival - self._prev_arrival) - (timestamp - self._prev_timestamp)
            self._jitter += (abs(delta) - self._jitter) / 16

        self._prev_arrival = arrival
        self._prev_timestamp = timestamp

class VoiceServer:
    """The background server responsible for communicating with Discord's voice servers."""

    __slots__ = (
        "_connection", "_ip", "_port", "_ssrc", "_udp", "_last_audio", "_watch_task", "_stats", "_buffers",
    )

    def __init__(
        self,
        connection: VoiceConnection,
    ) -> None:
        """
        Create a new voice server connection.

        Parameters
        ----------
        connection : VoiceConnection
            The voice connection handling this server.
        """

        self._connection: VoiceConnection = connection

        self._ip: str = None
        self._port: int = None
        self._ssrc: int = None
        self._udp: asyncio.DatagramTransport = None

        self._last_audio: dict[SSRC, float] = {}
        self._watch_task: asyncio.Task = None

        self._stats: dict[SSRC, RTPStats] = {}

        self._buffers: dict[SSRC, list[bytes]] = {}

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
        if len(data) < 12:
            return

        seq: int = struct.unpack_from(">H", data, 2)[0]
        timestamp: int = struct.unpack_from(">I", data, 4)[0]
        ssrc: int = struct.unpack_from(">I", data, 8)[0]

        if ssrc not in self._connection._client._ssrcsr:
            return

        if self._connection._config._record:
            opus: bytes = self._connection._decryption_mode(self._connection._secret, data)

            if self._connection._gateway._dave.ready:
                opus = self._connection._gateway._dave.decrypt(self._connection._client._ssrcsr[ssrc], opus)

            if ssrc in self._buffers:
                self._buffers[ssrc].append(opus)
            else:
                self._buffers[ssrc] = [opus]

        now: float = asyncio.get_running_loop().time()

        stats: RTPStats | None = self._stats.get(ssrc)
        if stats is None:
            stats = self._stats[ssrc] = RTPStats()

        stats.update(seq, timestamp, now)

        is_new: bool = ssrc not in self._last_audio
        self._last_audio[ssrc] = now

        if not is_new:
            return

        user_id: hikari.Snowflake = self._connection._client._ssrcsr[ssrc]
        channel_id: hikari.Snowflake = self._connection._client._members[user_id]

        channel: VoiceChannelMeta = self._connection._client._channels[channel_id]
        guild: hikari.Snowflake = channel.guild_id

        self._connection._client._event_factory.emit(
            MemberStartSpeakingEvent,
            channel_id=channel_id,
            guild_id=guild,
            member=channel.members[user_id],
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
                    self._stats.pop(ssrc, None)

                    user_id: hikari.Snowflake = self._connection._client._ssrcsr[ssrc]
                    channel_id: hikari.Snowflake = self._connection._client._members[user_id]

                    channel: VoiceChannelMeta = self._connection._client._channels[channel_id]
                    guild: hikari.Snowflake = channel.guild_id
                    member: hikari.Member = channel.members[user_id]

                    channel.active.remove(user_id)

                    self._connection._client._event_factory.emit(
                        MemberStopSpeakingEvent,
                        channel_id=channel,
                        guild_id=guild,
                        member=member,
                    )
                    if self._connection._config._record:
                        self._connection._client._event_factory.emit(
                            MemberSpeechEvent,
                            audio=self._buffers.pop(ssrc, []),
                            channel_id=channel,
                            guild_id=guild,
                            member=member,
                        )

                for ssrc, stats in self._stats.items():
                    if stats is None:
                        continue

                    jitter: float = stats._jitter / (Audio.SAMPLING_RATE // 1000)
                    total: int = stats._received + stats._lost
                    loss_rate: float = (stats._lost / total) if total else 0.0

                    user_id: hikari.Snowflake = None
                    channel_id: hikari.Snowflake = None
                    channel: VoiceChannelMeta = None
                    guild_id: hikari.Snowflake = None

                    if jitter > Audio.MAX_JITTER:
                        user_id = self._connection._client._ssrcsr[ssrc]
                        channel_id = self._connection._client._members[user_id]
                        channel = self._connection._client._channels[channel_id]
                        guild_id = channel.guild_id

                        self._connection._client._event_factory.emit(
                            VoiceWarningEvent,
                            channel_id=channel_id,
                            details=jitter,
                            guild_id=guild_id,
                            type=VoiceWarningType.JITTER,
                        )

                    if loss_rate > Audio.MAX_PACKET_LOSS:
                        user_id = self._connection._client._ssrcsr[ssrc]
                        channel_id = self._connection._client._members[user_id]
                        channel = self._connection._client._channels[channel_id]
                        guild_id = channel.guild_id

                        self._connection._client._event_factory.emit(
                            VoiceWarningEvent,
                            channel_id=channel_id,
                            details=loss_rate,
                            guild_id=guild_id,
                            type=VoiceWarningType.PACKET_LOSS,
                        )

                await asyncio.sleep(0.05)
        except asyncio.CancelledError as e:
            log_exception(e)
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

        if self._udp:
            return

        self._ip, self._port, self._ssrc = ip, port, ssrc

        logger.debug(f"Connecting to voice server: IP={ip}, Port={port}, SSRC={ssrc}")
        local_address: tuple[str, int] = await self._discover_ip()

        self._watch_task = self._connection._client._tasks.create(self._watch_silence(), name="server-watcher")

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
        self._stats.clear()

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

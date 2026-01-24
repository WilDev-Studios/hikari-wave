from __future__ import annotations

from dataclasses import dataclass
from enum import (
    IntEnum,
)
from hikariwave.internal.constants import CloseCode
from hikariwave.internal.signal import (
    DisconnectSignal,
    ReconnectSignal,
    ResumeSignal,
)
from typing import TYPE_CHECKING

import asyncio
import logging
import websockets

try:
    import orjson as json
except ImportError:
    import json

if TYPE_CHECKING:
    from typing import Any

__all__ = ()

logger: logging.Logger = logging.getLogger("hikari-wave.websocket")

class WebsocketPacket:
    """Base websocket packet implementation."""

@dataclass(frozen=True, slots=True)
class WebsocketPacketBytes(WebsocketPacket):
    """Bytes-structured websocket packet."""

    payload: bytes
    """The bytes packet payload."""

@dataclass(frozen=True, slots=True)
class WebsocketPacketJSON(WebsocketPacket):
    """JSON-structured websocket packet."""

    payload: dict[str, Any]
    """The JSON packet payload."""

class WebsocketState(IntEnum):
    """Websocket connection state."""

    CONNECTED     = 0
    """Websocket is currently connected."""
    CONNECTING    = 1
    """Websocket is currently connecting."""
    DISCONNECTED  = 2
    """Websocket is currently disconnected."""
    DISCONNECTING = 3
    """Websocket is currently disconnecting."""

class Websocket:
    """Custom websocket manager."""

    __slots__ = (
        "_websocket",
        "_state",
    )

    def __init__(self) -> None:
        """
        Create a new websocket.
        """
        
        self._websocket: websockets.ClientConnection = None
        self._state: WebsocketState = WebsocketState.DISCONNECTED
    
    def __close(self, exception: websockets.ConnectionClosed) -> None:
        if self._state in (WebsocketState.DISCONNECTING, WebsocketState.DISCONNECTED):
            raise DisconnectSignal()
        
        if exception.rcvd is None:
            raise ReconnectSignal()
        
        code: int = exception.rcvd.code

        match code:
            case (
                CloseCode.NORMAL |
                CloseCode.GOING_AWAY |
                CloseCode.UNKNOWN_OPCODE |
                CloseCode.FAILED_TO_DECODE_PAYLOAD |
                CloseCode.NOT_AUTHENTICATED |
                CloseCode.AUTHENTICATION_FAILED |
                CloseCode.ALREADY_AUTHENTICATED |
                CloseCode.SERVER_NOT_FOUND |
                CloseCode.UNKNOWN_PROTOCOL |
                CloseCode.DISCONNECTED |
                CloseCode.UNKNOWN_ENCRYPTION_MODE |
                CloseCode.BAD_REQUEST |
                CloseCode.DISCONNECTED_RATE_LIMITED |
                CloseCode.DISCONNECTED_CALL_TERMINATED
            ):
                raise DisconnectSignal()
            case (
                CloseCode.SESSION_NO_LONGER_VALID |
                CloseCode.SESSION_TIMEOUT
            ):
                raise ReconnectSignal()
            case CloseCode.VOICE_SERVER_CRASHED:
                raise ResumeSignal()
            case _:
                logger.error("Received unhandled close code {code}; disconnecting...")
                raise DisconnectSignal()

    async def __send(self, data: bytes | str) -> None:
        if self._state in (WebsocketState.DISCONNECTED, WebsocketState.DISCONNECTING):
            return DisconnectSignal()
        
        if self._state is not WebsocketState.CONNECTED:
            return ReconnectSignal()
        
        try:
            await self._websocket.send(data)
        except OSError:
            raise ResumeSignal()
        except websockets.ConnectionClosed as e:
            self.__close(e)

    async def connect(self, url: str) -> None:
        """
        Connect to a websocket endpoint.
        
        Parameters
        ----------
        url : str
            The URL/URI to connect to.
        
        Raises
        ------
        ReconnectSignal
            Error occurred and further attempts should be made to connect.
        """
        
        if self._state is not WebsocketState.DISCONNECTED:
            return
        
        self._state = WebsocketState.CONNECTING

        try:
            self._websocket = await websockets.connect(url)
        except (
            asyncio.TimeoutError |
            OSError |
            websockets.InvalidHandshake
        ):
            raise ReconnectSignal()
        
        self._state = WebsocketState.CONNECTED

    @property
    def connected(self) -> bool:
        """If the websocket is currently connected."""
        return self._state is WebsocketState.CONNECTED

    @property
    def connecting(self) -> bool:
        """If the websocket is currently connecting."""
        return self._state is WebsocketState.CONNECTING

    async def disconnect(self) -> None:
        """
        Disconnect the websocket.
        """

        if self._state in (WebsocketState.DISCONNECTED, WebsocketState.DISCONNECTING):
            return
        
        self._state = WebsocketState.DISCONNECTING

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        self._state = WebsocketState.DISCONNECTED
        
    @property
    def disconnected(self) -> bool:
        """If the websocket is currently disconnected."""
        return self._state is WebsocketState.DISCONNECTED

    @property
    def disconnecting(self) -> bool:
        """If the websocket is currently disconnecting."""
        return self._state is WebsocketState.DISCONNECTING

    async def receive(self) -> WebsocketPacket:
        """
        Block until a payload is received.
        
        Returns
        -------
        WebsocketPacket
            The received payload, either `bytes` or `JSON`.
        
        Raises
        ------
        DisconnectSignal
            Error occurred and no further attempts should be made to connect.
        ReconnectSignal
            Error occurred and further attempts should be made to connect.
        RuntimeError
            An unexpected payload type was received.
        ResumeSignal
            Error occurred and an attempt to resume the session should be made.
        """
        
        if self._state in (WebsocketState.DISCONNECTED, WebsocketState.DISCONNECTING):
            raise DisconnectSignal()

        if self._state is not WebsocketState.CONNECTED:
            raise ReconnectSignal()

        try:
            payload: str | bytes = await self._websocket.recv()
        except OSError:
            raise ResumeSignal()
        except websockets.ConnectionClosed as e:
            self.__close(e)
        
        if isinstance(payload, str):
            try:
                return WebsocketPacketJSON(json.loads(payload))
            except Exception:
                return WebsocketPacketJSON({})
        
        if isinstance(payload, bytes):
            return WebsocketPacketBytes(payload)
        
        error: str = f"Unexpected websocket payload type: {type(payload)!r}"
        raise RuntimeError(error)

    async def send_bytes(self, data: bytes) -> None:
        """
        Send a `bytes` payload through the websocket.
        
        Parameters
        ----------
        data : bytes
            The `bytes` payload to send.
        
        Raises
        ------
        DisconnectSignal
            Error occurred and no further attempts should be made to connect.
        ReconnectSignal
            Error occurred and further attempts should be made to connect.
        ResumeSignal
            Error occurred and an attempt to resume the session should be made.
        """

        await self.__send(data)

    async def send_json(self, data: dict[str, Any]) -> None:
        """
        Send a JSON payload through the websocket.
        
        Parameters
        ----------
        data : dict[str, Any]
            The JSON payload to send.
        
        Raises
        ------
        DisconnectSignal
            Error occurred and no further attempts should be made to connect.
        ReconnectSignal
            Error occurred and further attempts should be made to connect.
        ResumeSignal
            Error occurred and an attempt to resume the session should be made.
        """

        payload: dict[str, Any] | bytes = json.dumps(data)

        if json.__name__ == "orjson":
            payload = payload.decode("utf-8")

        await self.__send(payload)
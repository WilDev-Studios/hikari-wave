from __future__ import annotations

from enum import (
    auto,
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
import json
import logging
import websockets

if TYPE_CHECKING:
    from typing import Any

__all__ = ()

logger: logging.Logger = logging.getLogger("hikari-wave.websocket")

class WebsocketState(IntEnum):
    """Websocket connection state."""

    CONNECTED     = auto()
    """Websocket is currently connected."""
    CONNECTING    = auto()
    """Websocket is currently connecting."""
    DISCONNECTED  = auto()
    """Websocket is currently disconnected."""
    DISCONNECTING = auto()
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

    async def receive_json(self) -> dict[str, Any]:
        """
        Block until a JSON payload is received.
        
        Returns
        -------
        dict[str, Any]
            The JSON payload received.
        
        Raises
        ------
        DisconnectSignal
            Error occurred and no further attempts should be made to connect.
        ReconnectSignal
            Error occurred and further attempts should be made to connect.
        ResumeSignal
            Error occurred and an attempt to resume the session should be made.
        """
        
        if self._state in (WebsocketState.DISCONNECTED, WebsocketState.DISCONNECTING):
            raise DisconnectSignal()

        if self._state is not WebsocketState.CONNECTED:
            raise ReconnectSignal()

        try:
            payload: str = await self._websocket.recv()
        except OSError:
            raise ResumeSignal()
        except websockets.ConnectionClosed as e:
            self.__close(e)
        
        if not isinstance(payload, str):
            return {}
        
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

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

        if self._state in (WebsocketState.DISCONNECTED, WebsocketState.DISCONNECTING):
            raise DisconnectSignal()

        if self._state is not WebsocketState.CONNECTED:
            raise ReconnectSignal()
        
        try:
            await self._websocket.send(json.dumps(data))
        except OSError:
            raise ResumeSignal()
        except websockets.ConnectionClosed as e:
            self.__close(e)
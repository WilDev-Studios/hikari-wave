from __future__ import annotations

from enum import IntEnum
from typing import Final, Sequence

import io
import struct

__all__: Final[Sequence[str]] = (
    "Audio",
    "CloseCode",
    "Opcode",
)

class Audio:
    """Collection of audio-related constants."""

    BIT_16U: int = 2**16 - 1
    BIT_32U: int = 2**32 - 1
    BLOCKSIZE: int = io.DEFAULT_BUFFER_SIZE
    CHANNELS: int = 2
    FRAME_LENGTH: int = 20
    SAMPLE_SIZE: int = struct.calcsize('h') * CHANNELS
    SAMPLING_RATE: int = 48000
    SAMPLES_PER_FRAME: int = int(SAMPLING_RATE / 1000 * FRAME_LENGTH)

    FRAME_SIZE: int = SAMPLES_PER_FRAME * SAMPLE_SIZE

class CloseCode(IntEnum):
    """Collection of a voice close event codes."""

    UNKNOWN_OPCODE = 4001
    """Client sent an invalid opcode."""
    FAILED_TO_DECODE_PAYLOAD = 4002
    """Client send an invalid payload during IDENTIFY."""
    NOT_AUTHENTICATED = 4003
    """Client sent a payload before IDENTIFY."""
    AUTHENTICATION_FAILED = 4004
    """Client sent an incorrect token in IDENTIFY."""
    ALREADY_AUTHENTICATED = 4005
    """Client sent more than one IDENTIFY."""
    SESSION_NO_LONGER_VALID = 4006
    """Client session is not longer valid. Reconnection required."""
    SESSION_TIMEOUT = 4009
    """Client session timed out. Reconnection required."""
    SERVER_NOT_FOUND = 4011
    """Client attempted to connect to a server that wasn't found."""
    UNKNOWN_PROTOCOL = 4012
    """Client sent a protocol that is unrecognized by the server."""
    DISCONNECTED = 4014
    """Client was disconnected. No reconnection."""
    VOICE_SERVER_CRASHED = 4015
    """Server crashed. Resume required."""
    UNKNOWN_ENCRYPTION_MODE = 4016
    """Client sent an unrecognized encryption method."""
    BAD_REQUEST = 4020
    """Client send a malformed request."""
    DISCONNECTED_RATE_LIMITED = 4021
    """Client was disconnected due to rate limit being exceeded. No reconnection."""
    DISCONNECTED_CALL_TERMINATED = 4022
    """Client was disconnected due to call being terminated. No reconnection."""

class Opcode(IntEnum):
    """Collection of voice gateway operation codes."""

    IDENTIFY = 0
    """`CLIENT` - Begin a voice websocket connection."""
    SELECT_PROTOCOL = 1
    """`CLIENT` - Select the voice protocol."""
    READY = 2
    """`SERVER` - Complete the websocket handshake."""
    HEARTBEAT = 3
    """`CLIENT` - Keep the websocket connection alive."""
    SESSION_DESCRIPTION = 4
    """`SERVER` - Describe the session."""
    SPEAKING = 5
    """`CLIENT/SERVER` - Indicate which users are speaking."""
    HEARTBEAT_ACK = 6
    """`SERVER` - Sent to acknowledge a received client heartbeat."""
    RESUME = 7
    """`CLIENT` - Resume a connection."""
    HELLO = 8
    """`SERVER` - Time to wait between sending heartbeats in milliseconds."""
    RESUMED = 9
    """`SERVER` - Acknowledge a successful session resume."""
    CLIENTS_CONNECT = 11
    """`SERVER` - One or more clients have connection to the voice channel."""
    CLIENT_DISCONNECT = 13
    """`SERVER` - A client has disconnected from the voice channel."""
    UNDOCUMENTED_15 = 15
    """`SERVER` - Unknown as of `0.0.1a1`."""
    UNDOCUMENTED_18 = 18
    """`SERVER` - Unknown as of `0.0.1a1` - Contains user flags of user who joined channel."""
    UNDOCUMENTED_20 = 20
    """`SERVER` - Unknown as of `0.0.1a1` - Contains user platform of user who joined channel."""
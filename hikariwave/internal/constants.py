from __future__ import annotations

from enum import IntEnum

import io
import struct

__all__ = (
    "Audio",
    "CloseCode",
    "Constants",
    "Opcode",
)

class Audio:
    """Collection of audio-related constants."""

    BIT_16U: int = 2**16 - 1
    """16 bit, unsigned integer."""
    BIT_32U: int = 2**32 - 1
    """32 bit, unsigned integer."""
    BITRATE: str = "96k"
    """The audio bitrate."""
    BLOCKSIZE: int = io.DEFAULT_BUFFER_SIZE
    """FFmpeg blocksize."""
    CHANNELS: int = 2
    """Audio channels."""
    FRAME_LENGTH: int = 20
    """Length of Opus frame in milliseconds."""
    SAMPLE_SIZE: int = struct.calcsize('h') * CHANNELS
    """Size of frame sample."""
    SAMPLING_RATE: int = 48000
    """Sampling rate."""
    SAMPLES_PER_FRAME: int = int(SAMPLING_RATE / 1000 * FRAME_LENGTH)
    """Amount of samples per Opus frame."""

    FRAME_SIZE: int = SAMPLES_PER_FRAME * SAMPLE_SIZE
    """Total size of Opus frame."""

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

class Constants:
    """Collection of miscellaneous constants."""

    DAVE_VERSION: int = 0
    """The maximum supported `DAVE` version."""

class Opcode(IntEnum):
    """Collection of voice gateway operation codes."""

    IDENTIFY = 0
    """`CLIENT/JSON` - Begin a voice websocket connection."""
    SELECT_PROTOCOL = 1
    """`CLIENT/JSON` - Select the voice protocol."""
    READY = 2
    """`SERVER/JSON` - Complete the websocket handshake."""
    HEARTBEAT = 3
    """`CLIENT/JSON` - Keep the websocket connection alive."""
    SESSION_DESCRIPTION = 4
    """`SERVER/JSON` - Describe the session."""
    SPEAKING = 5
    """`CLIENT:SERVER/JSON` - Indicate which users are speaking."""
    HEARTBEAT_ACK = 6
    """`SERVER/JSON` - Sent to acknowledge a received client heartbeat."""
    RESUME = 7
    """`CLIENT/JSON` - Resume a connection."""
    HELLO = 8
    """`SERVER/JSON` - Time to wait between sending heartbeats in milliseconds."""
    RESUMED = 9
    """`SERVER/JSON` - Acknowledge a successful session resume."""
    CLIENTS_CONNECT = 11
    """`SERVER/JSON` - One or more clients have connection to the voice channel."""
    UNDOCUMENTED_12 = 12
    """`SERVER/JSON` - Unknown as of `0.1.0a1`."""
    CLIENT_DISCONNECT = 13
    """`SERVER/JSON` - A client has disconnected from the voice channel."""
    UNDOCUMENTED_15 = 15
    """`SERVER/JSON` - Unknown as of `0.0.1a1`."""
    UNDOCUMENTED_18 = 18
    """`SERVER/JSON` - Unknown as of `0.0.1a1` - Contains user flags of user who joined channel."""
    UNDOCUMENTED_20 = 20
    """`SERVER/JSON` - Unknown as of `0.0.1a1` - Contains user platform of user who joined channel."""
    DAVE_PREPARE_TRANSITION = 21
    """`SERVER/JSON` - A downgrade from the DAVE protocol is upcoming."""
    DAVE_EXECUTE_TRANSITION = 22
    """`SERVER/JSON` - Execute a previously announced protocol transition."""
    DAVE_TRANSITION_READY = 23
    """`CLIENT/JSON` - Acknowledge readiness previously announced transition."""
    DAVE_PREPARE_EPOCH = 24
    """`SERVER/JSON` - A DAVE protocol version or group change is upcoming."""
    DAVE_MLS_EXTERNAL_SENDER = 25
    """`SERVER/BYTE` - Credential and public key for MLS external sender."""
    DAVE_MLS_KEY_PACKAGE = 26
    """`CLIENT/BYTE` - MLS Key Package for pending group member."""
    DAVE_MLS_PROPOSALS = 27
    """`SERVER/BYTE` - MLS Proposals to be appended or revoked."""
    DAVE_MLS_COMMIT_WELCOME = 28
    """`CLIENT/BYTE` - MLS Commit with optional MLS welcome messages."""
    DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION = 29
    """`SERVER/BYTE` - MLS Commit to be processed for upcoming transition."""
    DAVE_MLS_WELCOME = 30
    """`SERVER/BYTE` - MLS Welcome to group for upcoming transition."""
    DAVE_MLS_INVALID_COMMIT_WELCOME = 31
    """`CLIENT/JSON` - Flag invalid commit or welcome, request re-add."""
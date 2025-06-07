from __future__ import annotations

import typing


__all__: typing.Sequence[str] = (
    "BIT_16",
    "BIT_32",
    "CHANNELS",
    "FRAME_LENGTH",
    "FRAME_SIZE",
    "SAMPLE_RATE",
    "WEBSOCKET_VERSION",
)

BIT_16: typing.Final[int] = 65536
"""65536 <=> 2^16."""

BIT_32: typing.Final[int] = 4_294_967_296
"""4,294,967,296 <=> 2^32."""

CHANNELS: typing.Final[int] = 2
"""The required amount of channels that Discord requires when sending voice streams."""

FRAME_LENGTH: typing.Final[int] = 20
"""The duration (ms) each frame is."""

FRAME_SIZE: typing.Final[int] = 960
"""The required size of each 20ms, 48kHz, stereo, PCM frame."""

PCM_FORMAT: typing.Final[str] = "s16le"
"""The format that FFmpeg requires to create PCM audio streams."""

SAMPLE_RATE: typing.Final[int] = 48000
"""The sample rate that Discord requires when sending voice streams."""

WEBSOCKET_VERSION: typing.Final[int] = 8
"""The voice websocket server version to connect to."""

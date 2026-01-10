"""
### hikari-wave: `0.4.0a1`\n
A lightweight, native voice implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.4.0a1\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

__version__ = "0.4.0a1"

def _silence_websockets_debug() -> None:
    import logging

    for name in (
        "websockets",
        "websockets.client",
        "websockets.server",
        "websockets.protocol",
    ):
        logger: logging.Logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)

_silence_websockets_debug()

from hikariwave.audio import *
from hikariwave.client import *
from hikariwave.config import *
from hikariwave.connection import *
from hikariwave.event import *
from hikariwave.internal import *
from hikariwave.networking import *
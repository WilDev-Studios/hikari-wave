"""
### hikari-wave: `0.0.1a2`\n
An asynchronous, type-safe, easy-to-use voice system implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.0.1a2\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

from .audio.player import AudioPlayer
from .audio.source import *
from .client import VoiceClient
from .connection import VoiceConnection
from .error import *
from .event.events import *
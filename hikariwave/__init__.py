"""
### hikari-wave: `0.0.1a3`\n
An asynchronous, type-safe, easy-to-use voice system implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.0.1a3\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source import *
from hikariwave.client import VoiceClient
from hikariwave.connection import VoiceConnection
from hikariwave.error import *
from hikariwave.event.events import *
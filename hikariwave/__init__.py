"""
### hikari-wave: `0.0.1a5`\n
A lightweight, native voice implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.0.1a5\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source import *
from hikariwave.client import VoiceClient
from hikariwave.connection import VoiceConnection
from hikariwave.event.events import *
from hikariwave.internal.error import *
from hikariwave.internal.result import Result, ResultReason
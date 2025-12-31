"""
### hikari-wave: `0.3.0a2`\n
A lightweight, native voice implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.3.0a2\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

from hikariwave.audio.player import AudioPlayer
from hikariwave.audio.source import *
from hikariwave.client import VoiceClient
from hikariwave.config import Config, BufferConfig, BufferMode
from hikariwave.connection import VoiceConnection
from hikariwave.event.events import *
from hikariwave.event.types import VoiceWarningType
from hikariwave.internal.error import *
from hikariwave.internal.result import Result, ResultReason

__version__ = "0.3.0a2"
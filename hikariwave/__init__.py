"""
### hikari-wave: `0.7.0a1`\n
A lightweight, native voice implementation for `hikari`-based Discord bots.

**Documentation:** https://hikari-wave.wildevstudios.net/en/0.7.0a1\n
**GitHub:** https://github.com/WilDev-Studios/hikari-wave
"""

__version__ = "0.7.0a1"
__all__ = (
    "AudioBeginEvent",
    "AudioBeginOrigin",
    "AudioElapsedEvent",
    "AudioEndEvent",
    "AudioEvent",
    "AudioPlaybackState",
    "AudioPlayer",
    "AudioSource",
    "BotEvent",
    "BotJoinEvent",
    "BotLeaveEvent",
    "BufferAudioSource",
    "BufferConfig",
    "BufferMode",
    "ClientError",
    "Config",
    "FileAudioSource",
    "GatewayError",
    "MemberDeafEvent",
    "MemberEvent",
    "MemberJoinEvent",
    "MemberLeaveEvent",
    "MemberMoveEvent",
    "MemberMuteEvent",
    "MemberSpeechEvent",
    "MemberStartSpeakingEvent",
    "MemberStopSpeakingEvent",
    "Result",
    "ResultReason",
    "ServerError",
    "URLAudioSource",
    "VoiceClient",
    "VoiceConnection",
    "VoiceEvent",
    "VoiceReconnectEvent",
    "VoiceWarningEvent",
    "VoiceWarningType",
    "YouTubeAudioSource",
    "WaveEvent",
)

from hikariwave.audio import (
    AudioPlaybackState,
    AudioPlayer,
    AudioSource,
    BufferAudioSource,
    FileAudioSource,
    URLAudioSource,
    YouTubeAudioSource,
)
from hikariwave.client import VoiceClient
from hikariwave.config import (
    BufferConfig,
    BufferMode,
    Config,
)
from hikariwave.connection import VoiceConnection
from hikariwave.event import (
    AudioBeginEvent,
    AudioBeginOrigin,
    AudioElapsedEvent,
    AudioEndEvent,
    AudioEvent,
    BotEvent,
    BotJoinEvent,
    BotLeaveEvent,
    MemberDeafEvent,
    MemberEvent,
    MemberJoinEvent,
    MemberLeaveEvent,
    MemberMoveEvent,
    MemberMuteEvent,
    MemberSpeechEvent,
    MemberStartSpeakingEvent,
    MemberStopSpeakingEvent,
    VoiceEvent,
    VoiceReconnectEvent,
    VoiceWarningEvent,
    VoiceWarningType,
    WaveEvent,
)
from hikariwave.internal import (
    ClientError,
    GatewayError,
    Result,
    ResultReason,
    ServerError,
)

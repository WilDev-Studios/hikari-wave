from __future__ import annotations

from dataclasses import dataclass
from hikariwave.audio.source.base import AudioSource
from hikariwave.event.events.base import WaveEvent
from hikariwave.event.types import AudioBeginOrigin

__all__ = (
    "AudioEvent",
    "AudioBeginEvent",
    "AudioElapsedEvent",
    "AudioEndEvent",
)

@dataclass(frozen=True, init=False, slots=True)
class AudioEvent(WaveEvent):
    """Base audio event implementation."""

    audio: AudioSource
    """The audio this event is referencing."""

@dataclass(frozen=True, init=False, slots=True)
class AudioBeginEvent(AudioEvent):
    """Dispatched when audio begins playing in a voice channel."""

    origin: AudioBeginOrigin
    """The origin from which this audio is being played."""

@dataclass(frozen=True, init=False, slots=True)
class AudioElapsedEvent(AudioEvent):
    """Dispatched when audio progresses."""

    hours: int
    """The total amount of hours elapsed."""
    minutes: int
    """The total amount of minutes elapsed."""
    seconds: int
    """The total amount of seconds elapsed."""

@dataclass(frozen=True, init=False, slots=True)
class AudioEndEvent(AudioEvent):
    """Dispatched when audio stops playing in a voice channel."""

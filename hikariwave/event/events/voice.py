from __future__ import annotations

from dataclasses import dataclass
from hikariwave.event.events.base import WaveEvent
from hikariwave.event.types import VoiceWarningType

__all__ = (
    "VoiceEvent",
    "VoiceReconnectEvent",
    "VoiceWarningEvent",
)

@dataclass(frozen=True, init=False, slots=True)
class VoiceEvent(WaveEvent):
    """Base voice event implementation."""

@dataclass(frozen=True, init=False, slots=True)
class VoiceReconnectEvent(VoiceEvent):
    """Dispatched when a voice connection reconnects or resumes."""

@dataclass(frozen=True, init=False, slots=True)
class VoiceWarningEvent(VoiceEvent):
    """Dispatched when non-fatal voice issues occur (packet loss, jitter, latency)."""

    type: VoiceWarningType
    """The type of warning that was issued."""
    details: str | int | None = None
    """Any contextual information that may be provided."""
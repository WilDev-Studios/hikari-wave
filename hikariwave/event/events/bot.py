from __future__ import annotations

from dataclasses import dataclass
from hikariwave.event.events.base import WaveEvent

import hikari

__all__ = (
    "BotEvent",
    "BotJoinEvent",
    "BotLeaveEvent"
)

@dataclass(frozen=True, init=False, slots=True)
class BotEvent(WaveEvent):
    """Base bot event implementation."""

    bot: hikari.GatewayBot
    """The bot instance referencing this event."""

@dataclass(frozen=True, init=False, slots=True)
class BotJoinEvent(BotEvent):
    """Dispatched when the bot joins a voice channel."""

    is_deaf: bool
    """If the bot is deafened."""
    is_mute: bool
    """If the bot is muted."""

@dataclass(frozen=True, init=False, slots=True)
class BotLeaveEvent(BotEvent):
    """Dispatched when the bot leaves a voice channel."""

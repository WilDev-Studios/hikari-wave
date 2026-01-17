from __future__ import annotations

from dataclasses import dataclass

import hikari

__all__ = ("WaveEvent",)

@dataclass(frozen=True, init=False, slots=True)
class WaveEvent(hikari.Event):
    """Base event listener for all `hikari-wave` supplemental events, for convenience."""

    channel_id: hikari.Snowflake
    """The ID of the channel."""
    guild_id: hikari.Snowflake
    """The ID of the guild the channel is in."""

    @property
    def app(self) -> hikari.RESTAware:
        return super().app
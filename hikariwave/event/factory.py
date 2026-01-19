from __future__ import annotations

from hikariwave.event.events.base import WaveEvent
from typing import (
    TYPE_CHECKING,
    TypeVar,
)

import hikari

if TYPE_CHECKING:
    from typing import Any

__all__ = ()

WaveEventType = TypeVar("WaveEvent", bound=WaveEvent)

class EventFactory:
    """Responsible for emitting and handling all supplemental events."""

    __slots__ = (
        "_bot",
    )

    def __init__(self, bot: hikari.GatewayBot) -> None:
        """
        Create a new event factory.
        
        Parameters
        ----------
        bot : hikari.GatewayBot
            The OAuth2 bot to use for dispatching events.
        """
        
        self._bot: hikari.GatewayBot = bot
    
    def emit(self, event: type[WaveEventType], **kwargs: Any) -> None:
        """
        Dispatch an event.
        
        Parameters
        ----------
        event : type[WaveEvent]
            The `hikari-wave` event to dispatch.
        kwargs : Any
            The key-value pairs of data to send directly to the event constructor.
        """

        instance: WaveEventType = object.__new__(event)
        for key, value in kwargs.items():
            object.__setattr__(instance, key, value)
        
        self._bot.dispatch(instance)
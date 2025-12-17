from __future__ import annotations

from hikariwave.event import events
from hikariwave.event.types import WaveEventType
from typing import Callable, Final, Sequence, TypeAlias

import hikari

__all__: Final[Sequence[str]] = ("EventFactory",)

EventBuilder: TypeAlias = Callable[[tuple], events.WaveEvent]

class EventFactory:
    """Responsible for emitting and handling all supplemental events."""

    __slots__ = (
        "_bot",
        "_builders",
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
        self._builders: dict[WaveEventType, EventBuilder] = {}

        for type_, event in {
            WaveEventType.AUDIO_BEGIN: events.AudioBeginEvent,
            WaveEventType.AUDIO_END: events.AudioEndEvent,
            WaveEventType.BOT_JOIN_VOICE: events.BotJoinVoiceEvent,
            WaveEventType.BOT_LEAVE_VOICE: events.BotLeaveVoiceEvent,
            WaveEventType.MEMBER_DEAF: events.MemberDeafEvent,
            WaveEventType.MEMBER_JOIN_VOICE: events.MemberJoinVoiceEvent,
            WaveEventType.MEMBER_LEAVE_VOICE: events.MemberLeaveVoiceEvent,
            WaveEventType.MEMBER_MOVE_VOICE: events.MemberMoveVoiceEvent,
            WaveEventType.MEMBER_MUTE: events.MemberMuteEvent,
            WaveEventType.MEMBER_START_SPEAKING: events.MemberStartSpeakingEvent,
            WaveEventType.MEMBER_STOP_SPEAKING: events.MemberStopSpeakingEvent,
            WaveEventType.VOICE_RECONNECT: events.VoiceReconnectEvent,
            WaveEventType.VOICE_WARNING: events.VoiceWarningEvent,
        }.items():
            self._builders[type_] = event._create
    
    def emit(self, key: WaveEventType, *args) -> None:
        """
        Emit a supplemental event.
        
        Parameters
        ----------
        key : WaveEventType
            The type of supplemental event to emit.
        args : tuple
            Any arguments needed in the instantiation of such event.
        
        Raises
        ------
        KeyError
            If the provided key doesn't correspond to a supplemental event.
        """
        
        try:
            self._bot.dispatch(self._builders[key](*args))
        except KeyError:
            error: str = f"No event registered for key {key!r}"
            raise RuntimeError(error)
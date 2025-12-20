from __future__ import annotations

from dataclasses import dataclass
from enum import auto, IntEnum

__all__ = (
    "Result",
    "ResultReason",
)

class ResultReason(IntEnum):
    """Reasons for a failed result state."""

    EMPTY_HISTORY = auto()
    """The audio history was empty."""
    EMPTY_QUEUE = auto()
    """The audio queue was empty."""
    NO_TRACK = auto()
    """No audio is currently playing."""
    NOT_FOUND = auto()
    """The requested object could not be found."""
    PAUSED = auto()
    """The player is not currently playing."""
    PLAYING = auto()
    """The player is currently playing."""

@dataclass(frozen=True, slots=True)
class Result:
    """
    The output of a method for UX.
    
    Can be silently ignored or used for further functionality.
    """

    success: bool
    """If the method succeeded."""
    reason: ResultReason | None
    """The reason for a failed state, if failed."""

    @staticmethod
    def failed(reason: ResultReason) -> Result:
        """Create a `FAILED` result."""
        return Result(False, reason)

    @staticmethod
    def succeeded() -> Result:
        """Create an `SUCCEEDED` result."""
        return Result(True, None)
from __future__ import annotations

__all__ = ()

class DisconnectSignal(Exception):
    """Signal to disconnect."""

class ReconnectSignal(Exception):
    """Signal to reconnect."""

class ResumeSignal(Exception):
    """Signal to resume."""

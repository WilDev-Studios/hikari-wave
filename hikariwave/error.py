from __future__ import annotations

from typing import Final, Sequence

__all__: Final[Sequence[str]] = (
    "GatewayError",
    "ServerError",
)

class GatewayError(Exception):
    """Raised when an error occurs with a voice system gateway."""

class ServerError(Exception):
    """Raised when an error occurs with a voice system server."""
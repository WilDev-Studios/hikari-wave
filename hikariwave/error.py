from __future__ import annotations

__all__ = (
    "GatewayError",
    "ServerError",
)

class GatewayError(Exception):
    """Raised when an error occurs with a voice system gateway."""

class ServerError(Exception):
    """Raised when an error occurs with a voice system server."""
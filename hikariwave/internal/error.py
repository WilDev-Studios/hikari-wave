from __future__ import annotations

__all__ = (
    "ClientError",
    "GatewayError",
    "ServerError",
)

class ClientError(Exception):
    """Raised when an error occurs with a voice client."""

class GatewayError(Exception):
    """Raised when an error occurs with a voice system gateway."""

class ServerError(Exception):
    """Raised when an error occurs with a voice system server."""
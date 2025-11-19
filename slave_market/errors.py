"""Custom exception hierarchy for the plugin."""

from __future__ import annotations


class GameError(RuntimeError):
    """Base exception the handlers map to friendly replies."""


class PermissionDenied(GameError):
    """Raised when the user attempts to perform an admin only operation."""


class NotFound(GameError):
    """Raised when a requested resource could not be located."""


__all__ = ["GameError", "PermissionDenied", "NotFound"]

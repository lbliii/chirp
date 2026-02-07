"""Chirp exception hierarchy.

Shared across Router, App, handler, and middleware so every module
raises and catches the same types.
"""

from dataclasses import dataclass


class ChirpError(Exception):
    """Base for all chirp-specific errors."""


class ConfigurationError(ChirpError):
    """Raised when app configuration is invalid.

    Typically caught during ``App._freeze()`` at startup.
    """


@dataclass(frozen=True, slots=True)
class HTTPError(ChirpError):
    """An error that maps directly to an HTTP status code.

    Raised by the router, middleware, or handlers. The ASGI handler
    catches these and dispatches to the matching ``@app.error()`` handler.
    """

    status: int
    detail: str = ""
    headers: tuple[tuple[str, str], ...] = ()

    def __str__(self) -> str:
        if self.detail:
            return f"{self.status}: {self.detail}"
        return str(self.status)


class NotFound(HTTPError):
    """404 — no route matched the request path."""

    def __init__(self, detail: str = "Not Found") -> None:
        super().__init__(status=404, detail=detail)


class MethodNotAllowed(HTTPError):
    """405 — route exists but not for this HTTP method.

    Includes an ``Allow`` header listing the valid methods.
    """

    def __init__(self, allowed: frozenset[str], detail: str = "Method Not Allowed") -> None:
        allow_value = ", ".join(sorted(allowed))
        super().__init__(
            status=405,
            detail=detail,
            headers=(("Allow", allow_value),),
        )

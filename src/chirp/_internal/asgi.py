"""Typed ASGI definitions.

Replaces the standard Scope = MutableMapping[str, Any] with typed
dataclasses for internal use. Users never see these.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, TypeAlias

# Raw ASGI types (matching the spec)
Scope: TypeAlias = MutableMapping[str, Any]
Receive: TypeAlias = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send: TypeAlias = Callable[[MutableMapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HTTPScope:
    """Typed HTTP scope parsed from raw ASGI scope dict.

    Internal only -- users interact with Request, not this.
    """

    type: str
    asgi: dict[str, str]
    http_version: str
    method: str
    path: str
    raw_path: bytes
    query_string: bytes
    root_path: str
    headers: tuple[tuple[bytes, bytes], ...]
    server: tuple[str, int] | None
    client: tuple[str, int] | None

    @classmethod
    def from_scope(cls, scope: Scope) -> "HTTPScope":
        """Parse raw ASGI scope into typed object."""
        server = scope.get("server")
        client = scope.get("client")
        return cls(
            type=scope["type"],
            asgi=scope["asgi"],
            http_version=scope.get("http_version", "1.1"),
            method=scope["method"],
            path=scope["path"],
            raw_path=scope.get("raw_path", b""),
            query_string=scope.get("query_string", b""),
            root_path=scope.get("root_path", ""),
            headers=tuple(scope.get("headers", ())),
            server=tuple(server) if server else None,
            client=tuple(client) if client else None,
        )

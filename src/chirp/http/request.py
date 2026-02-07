"""Immutable HTTP request.

Frozen metadata with async body access. The request is honest about
what it is: received data that doesn't change.
"""

from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from typing import Any

from chirp._internal.asgi import Receive
from chirp.http.cookies import parse_cookies
from chirp.http.headers import Headers
from chirp.http.query import QueryParams


@dataclass(frozen=True, slots=True)
class Request:
    """An immutable HTTP request.

    Metadata (method, path, headers, etc.) is frozen at creation.
    Body is accessed asynchronously via ``.body()``, ``.json()``, ``.form()``.

    Cookies are parsed once at creation time (in ``from_asgi``) and stored
    as a frozen field — not re-parsed on every access.
    """

    method: str
    path: str
    headers: Headers
    query: QueryParams
    path_params: dict[str, str]
    http_version: str
    server: tuple[str, int] | None
    client: tuple[str, int] | None
    cookies: Mapping[str, str]

    # Private: ASGI receive callable for body streaming
    _receive: Receive

    # -- Computed properties --

    @property
    def is_fragment(self) -> bool:
        """True if this is an htmx fragment request (HX-Request header)."""
        return self.headers.get("hx-request") == "true"

    @property
    def htmx_target(self) -> str | None:
        """The target element ID from HX-Target header."""
        return self.headers.get("hx-target")

    @property
    def htmx_trigger(self) -> str | None:
        """The trigger element ID from HX-Trigger header."""
        return self.headers.get("hx-trigger")

    @property
    def content_type(self) -> str | None:
        """The Content-Type header value."""
        return self.headers.get("content-type")

    @property
    def content_length(self) -> int | None:
        """The Content-Length header as int."""
        value = self.headers.get("content-length")
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def url(self) -> str:
        """Full request URL (path + query string)."""
        qs = self.query._raw
        if qs:
            return f"{self.path}?{qs.decode('latin-1')}"
        return self.path

    # -- Async body access --

    async def body(self) -> bytes:
        """Read the full request body."""
        chunks = [chunk async for chunk in self.stream()]
        return b"".join(chunks)

    async def stream(self) -> AsyncGenerator[bytes]:
        """Stream the request body in chunks."""
        while True:
            message = await self._receive()
            body = message.get("body", b"")
            if body:
                yield body
            if not message.get("more_body", False):
                break

    async def json(self) -> Any:
        """Parse the body as JSON."""
        import json as json_module

        raw = await self.body()
        return json_module.loads(raw)

    async def text(self) -> str:
        """Read the body as text (UTF-8)."""
        raw = await self.body()
        return raw.decode("utf-8")

    # -- Factory --

    @classmethod
    def from_asgi(
        cls,
        scope: dict[str, Any],
        receive: Receive,
        path_params: dict[str, str] | None = None,
    ) -> Request:
        """Create a Request from an ASGI scope and receive callable."""
        headers = Headers(tuple(scope.get("headers", ())))
        server = scope.get("server")
        client = scope.get("client")
        return cls(
            method=scope["method"],
            path=scope["path"],
            headers=headers,
            query=QueryParams(scope.get("query_string", b"")),
            path_params=path_params or {},
            http_version=scope.get("http_version", "1.1"),
            server=tuple(server) if server else None,
            client=tuple(client) if client else None,
            cookies=parse_cookies(headers.get("cookie", "")),
            _receive=receive,
        )

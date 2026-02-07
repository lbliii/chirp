"""HTTP response with chainable .with_*() transformation API.

Each transformation returns a new Response. Immutable by convention,
built incrementally by design.
"""

from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from chirp.http.cookies import SetCookie


@dataclass(frozen=True, slots=True)
class Response:
    """An HTTP response built through immutable transformations.

    Construct with a body, then chain ``.with_*()`` calls to set
    status, headers, and cookies. Each call returns a new ``Response``.
    """

    body: str | bytes = ""
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()
    cookies: tuple[SetCookie, ...] = ()

    # -- Chainable transformations --

    def with_status(self, status: int) -> Response:
        """Return a new Response with a different status code."""
        return replace(self, status=status)

    def with_header(self, name: str, value: str) -> Response:
        """Return a new Response with an additional header."""
        return replace(self, headers=(*self.headers, (name, value)))

    def with_headers(self, headers: Mapping[str, str]) -> Response:
        """Return a new Response with additional headers."""
        new = tuple(headers.items())
        return replace(self, headers=(*self.headers, *new))

    def with_content_type(self, content_type: str) -> Response:
        """Return a new Response with a different content type."""
        return replace(self, content_type=content_type)

    def with_cookie(
        self,
        name: str,
        value: str,
        *,
        max_age: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = True,
        samesite: str = "lax",
    ) -> Response:
        """Return a new Response with an additional Set-Cookie."""
        cookie = SetCookie(
            name=name,
            value=value,
            max_age=max_age,
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
        )
        return replace(self, cookies=(*self.cookies, cookie))

    def without_cookie(self, name: str, path: str = "/") -> Response:
        """Return a new Response that deletes a cookie (Max-Age=0)."""
        cookie = SetCookie(name=name, value="", max_age=0, path=path)
        return replace(self, cookies=(*self.cookies, cookie))

    # -- Body helpers --

    @property
    def body_bytes(self) -> bytes:
        """Body as bytes."""
        if isinstance(self.body, str):
            return self.body.encode("utf-8")
        return self.body

    @property
    def text(self) -> str:
        """Body as string."""
        if isinstance(self.body, bytes):
            return self.body.decode("utf-8")
        return self.body


@dataclass(frozen=True, slots=True)
class Redirect:
    """A redirect response."""

    url: str
    status: int = 302
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class StreamingResponse:
    """A streaming HTTP response that sends chunks progressively.

    Used for chunked transfer encoding: headers are sent immediately,
    then each chunk is sent as an ASGI body message with ``more_body=True``.

    Supports the same ``.with_*()`` chainable API as ``Response``
    so middleware can modify headers/status without knowing the
    response is streamed.
    """

    chunks: Iterator[str] | AsyncIterator[str]
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()

    def with_status(self, status: int) -> StreamingResponse:
        """Return a new StreamingResponse with a different status code."""
        return replace(self, status=status)

    def with_header(self, name: str, value: str) -> StreamingResponse:
        """Return a new StreamingResponse with an additional header."""
        return replace(self, headers=(*self.headers, (name, value)))

    def with_headers(self, headers: Mapping[str, str]) -> StreamingResponse:
        """Return a new StreamingResponse with additional headers."""
        new = tuple(headers.items())
        return replace(self, headers=(*self.headers, *new))

    def with_content_type(self, content_type: str) -> StreamingResponse:
        """Return a new StreamingResponse with a different content type."""
        return replace(self, content_type=content_type)


@dataclass(frozen=True, slots=True)
class SSEResponse:
    """Sentinel response for Server-Sent Events.

    Wraps an EventStream and requires direct ASGI send/receive access
    (the handler bypasses the normal _send_response path).

    Provides no-op ``.with_*()`` methods so middleware chains don't crash.
    SSE headers (text/event-stream, no-cache) are always sent by the SSE
    handler itself; any middleware header modifications are ignored.
    """

    event_stream: Any  # EventStream (avoided import cycle)
    kida_env: Any = None  # kida Environment | None

    def with_status(self, status: int) -> SSEResponse:  # noqa: ARG002
        """No-op: SSE always sends 200."""
        return self

    def with_header(self, name: str, value: str) -> SSEResponse:  # noqa: ARG002
        """No-op: SSE headers are fixed by the protocol handler."""
        return self

    def with_headers(self, headers: Mapping[str, str]) -> SSEResponse:  # noqa: ARG002
        """No-op: SSE headers are fixed by the protocol handler."""
        return self

    def with_content_type(self, content_type: str) -> SSEResponse:  # noqa: ARG002
        """No-op: SSE content type is always text/event-stream."""
        return self

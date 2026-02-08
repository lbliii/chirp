"""HTTP response with chainable .with_*() transformation API.

Each transformation returns a new Response. Immutable by convention,
built incrementally by design.
"""

import json as json_module
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

    # -- htmx response headers --

    def with_hx_redirect(self, url: str) -> Response:
        """Tell htmx to do a full-page redirect (like entering a URL).

        Sets the ``HX-Redirect`` response header.
        """
        return self.with_header("HX-Redirect", url)

    def with_hx_location(
        self,
        url: str,
        *,
        target: str | None = None,
        swap: str | None = None,
        source: str | None = None,
    ) -> Response:
        """Tell htmx to navigate via AJAX (like clicking a boosted link).

        When only *url* is provided, sets ``HX-Location`` to the plain
        URL string.  When *target*, *swap*, or *source* are given, sets
        the header to a JSON object with the specified fields.
        """
        if target is None and swap is None and source is None:
            return self.with_header("HX-Location", url)
        obj: dict[str, str] = {"path": url}
        if target is not None:
            obj["target"] = target
        if swap is not None:
            obj["swap"] = swap
        if source is not None:
            obj["source"] = source
        return self.with_header("HX-Location", json_module.dumps(obj))

    def with_hx_retarget(self, selector: str) -> Response:
        """Override the target element for this response.

        Sets the ``HX-Retarget`` response header to a CSS selector.
        """
        return self.with_header("HX-Retarget", selector)

    def with_hx_reswap(self, strategy: str) -> Response:
        """Override the swap strategy for this response.

        Sets the ``HX-Reswap`` response header.  Accepts any valid
        ``hx-swap`` value (e.g. ``"innerHTML"``, ``"outerHTML"``,
        ``"beforeend"``).
        """
        return self.with_header("HX-Reswap", strategy)

    def with_hx_trigger(self, event: str | dict[str, Any]) -> Response:
        """Trigger a client-side event after the response is received.

        Sets the ``HX-Trigger`` response header.  Accepts a plain
        event name string or a dict for events with payloads::

            .with_hx_trigger("closeModal")
            .with_hx_trigger({"showToast": {"message": "Saved!"}})
        """
        value = event if isinstance(event, str) else json_module.dumps(event)
        return self.with_header("HX-Trigger", value)

    def with_hx_trigger_after_settle(self, event: str | dict[str, Any]) -> Response:
        """Trigger a client-side event after the settle step.

        Sets the ``HX-Trigger-After-Settle`` response header.
        """
        value = event if isinstance(event, str) else json_module.dumps(event)
        return self.with_header("HX-Trigger-After-Settle", value)

    def with_hx_trigger_after_swap(self, event: str | dict[str, Any]) -> Response:
        """Trigger a client-side event after the swap step.

        Sets the ``HX-Trigger-After-Swap`` response header.
        """
        value = event if isinstance(event, str) else json_module.dumps(event)
        return self.with_header("HX-Trigger-After-Swap", value)

    def with_hx_push_url(self, url: str | bool) -> Response:
        """Push a URL into the browser history stack.

        Sets the ``HX-Push-Url`` response header.  Pass a URL string
        or ``False`` to prevent htmx from pushing.
        """
        value = url if isinstance(url, str) else ("true" if url else "false")
        return self.with_header("HX-Push-Url", value)

    def with_hx_replace_url(self, url: str | bool) -> Response:
        """Replace the current URL in the browser location bar.

        Sets the ``HX-Replace-Url`` response header.  Pass a URL
        string or ``False`` to prevent htmx from replacing.
        """
        value = url if isinstance(url, str) else ("true" if url else "false")
        return self.with_header("HX-Replace-Url", value)

    def with_hx_refresh(self) -> Response:
        """Tell htmx to do a full page refresh.

        Sets ``HX-Refresh: true``.
        """
        return self.with_header("HX-Refresh", "true")

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

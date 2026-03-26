"""Immutable HTTP request.

Frozen metadata with async body access. The request is honest about
what it is: received data that doesn't change.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from chirp._internal.asgi import Receive, Scope
from chirp.http.cookies import parse_cookies
from chirp.http.headers import Headers
from chirp.http.query import QueryParams

if TYPE_CHECKING:
    from chirp.http.forms import FormData


class HtmxDetails:
    """Parsed htmx request headers with caching.

    Attached to ``request.htmx``. Truthy when ``HX-Request`` is present,
    providing typed access to all htmx request headers. Values are
    computed once and cached for the lifetime of the request.
    """

    __slots__ = ("_cache", "_headers", "_server")

    _headers: Headers
    _server: tuple[str, int] | None
    _cache: dict[str, str | None]

    def __init__(self, headers: Headers, server: tuple[str, int] | None) -> None:
        self._headers = headers
        self._server = server
        self._cache = {}

    def __bool__(self) -> bool:
        """True if this is an htmx request (HX-Request header is present)."""
        return self._headers.get("hx-request") == "true"

    def _get(self, name: str) -> str | None:
        """Read an htmx header with URI-AutoEncoded decoding and caching."""
        if name in self._cache:
            return self._cache[name]
        value = self._headers.get(name)
        if value is None:
            self._cache[name] = None
            return None
        if self._headers.get(f"{name}-uri-autoencoded") == "true":
            value = unquote(value)
        self._cache[name] = value
        return value

    @property
    def boosted(self) -> bool:
        """True if this request came from an hx-boost enhanced element."""
        return self._headers.get("hx-boosted") == "true"

    @property
    def history_restore(self) -> bool:
        """True if htmx is restoring from history (cache miss on back/forward)."""
        return self._headers.get("hx-history-restore-request") == "true"

    @property
    def target(self) -> str | None:
        """The target element ID from HX-Target header."""
        return self._get("hx-target")

    @property
    def trigger(self) -> str | None:
        """The trigger element ID from HX-Trigger header."""
        return self._get("hx-trigger")

    @property
    def trigger_name(self) -> str | None:
        """The name attribute of the trigger element (HX-Trigger-Name header)."""
        return self._get("hx-trigger-name")

    @property
    def current_url(self) -> str | None:
        """The browser's current URL from HX-Current-URL header."""
        return self._get("hx-current-url")

    @property
    def current_url_abs_path(self) -> str | None:
        """The path portion of the browser's current URL.

        Strips scheme and host when the origin matches this request's
        server, returning just the path (+ query + fragment). Returns
        the full URL unchanged when the origin differs or server info
        is unavailable.
        """
        key = "_current_url_abs_path"
        if key in self._cache:
            return self._cache[key]
        url = self.current_url
        if url is None:
            self._cache[key] = None
            return None
        parsed = urlparse(url)
        server = self._server
        if server is not None:
            host, port = server
            request_host = f"{host}:{port}" if port not in (80, 443) else host
            if parsed.netloc == request_host:
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                if parsed.fragment:
                    path = f"{path}#{parsed.fragment}"
                self._cache[key] = path
                return path
        self._cache[key] = url
        return url

    @property
    def prompt(self) -> str | None:
        """The user response to hx-prompt (HX-Prompt header)."""
        return self._get("hx-prompt")

    @property
    def partial(self) -> str | None:
        """The partial element name from HX-Partial header (htmx 4.0+).

        Set when the request originates from an ``<htmx-partial>`` element.
        """
        return self._get("hx-partial")


class _LazyQueryParams(Mapping[str, str]):
    """QueryParams that parses on first access."""

    __slots__ = ("_parsed", "_raw")

    def __init__(self, raw: bytes) -> None:
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_parsed", None)

    def _ensure(self) -> QueryParams:
        parsed = object.__getattribute__(self, "_parsed")
        if parsed is None:
            parsed = QueryParams(object.__getattribute__(self, "_raw"))
            object.__setattr__(self, "_parsed", parsed)
        return parsed

    def __getitem__(self, key: str) -> str:
        return self._ensure()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._ensure()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._ensure())

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return self._ensure().get(key, default)

    def get_list(self, key: str) -> list[str]:
        return self._ensure().get_list(key)

    def get_int(self, key: str, default: int | None = None) -> int | None:
        return self._ensure().get_int(key, default)

    def get_bool(self, key: str, default: bool | None = None) -> bool | None:
        return self._ensure().get_bool(key, default)


class _LazyCookies(Mapping[str, str]):
    """Cookies that parse on first access."""

    __slots__ = ("_cookie_header", "_parsed")

    def __init__(self, cookie_header: str) -> None:
        object.__setattr__(self, "_cookie_header", cookie_header)
        object.__setattr__(self, "_parsed", None)

    def _ensure(self) -> dict[str, str]:
        parsed = object.__getattribute__(self, "_parsed")
        if parsed is None:
            parsed = parse_cookies(object.__getattribute__(self, "_cookie_header"))
            object.__setattr__(self, "_parsed", parsed)
        return parsed

    def __getitem__(self, key: str) -> str:
        return self._ensure()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._ensure()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._ensure())

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return self._ensure().get(key, default)


@dataclass(frozen=True, slots=True)
class Request:
    """An immutable HTTP request.

    Metadata (method, path, headers, etc.) is frozen at creation.
    Body is accessed asynchronously via ``.body()``, ``.json()``, ``.form()``.

    Query params and cookies are parsed lazily on first access (not at creation).
    """

    method: str
    path: str
    headers: Headers
    query: QueryParams | _LazyQueryParams
    path_params: dict[str, str]
    http_version: str
    server: tuple[str, int] | None
    client: tuple[str, int] | None
    cookies: Mapping[str, str] | _LazyCookies
    request_id: str  # X-Request-ID from header or generated UUID

    # Private: ASGI receive callable for body streaming
    _receive: Receive

    # Private: mutable cache for body and parsed form data
    # (dict contents are mutable even though the field reference is frozen)
    _cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # -- Computed properties --

    @property
    def htmx(self) -> HtmxDetails:
        """Typed, cached htmx request details.

        Truthy when ``HX-Request`` is present::

            if request.htmx:
                target = request.htmx.target
        """
        if "_htmx" not in self._cache:
            self._cache["_htmx"] = HtmxDetails(self.headers, self.server)
        return self._cache["_htmx"]

    # -- Convenience aliases (delegate to request.htmx) --

    @property
    def is_fragment(self) -> bool:
        """True if this is an htmx fragment request (HX-Request header)."""
        return bool(self.htmx)

    @property
    def is_history_restore(self) -> bool:
        """True if htmx is restoring from history (cache miss on back/forward)."""
        return self.htmx.history_restore

    @property
    def is_boosted(self) -> bool:
        """True if this request came from an hx-boost enhanced element."""
        return self.htmx.boosted

    @property
    def htmx_target(self) -> str | None:
        """The target element ID from HX-Target header."""
        return self.htmx.target

    @property
    def htmx_trigger(self) -> str | None:
        """The trigger element ID from HX-Trigger header."""
        return self.htmx.trigger

    @property
    def htmx_trigger_name(self) -> str | None:
        """The name attribute of the trigger element (HX-Trigger-Name header)."""
        return self.htmx.trigger_name

    @property
    def htmx_current_url(self) -> str | None:
        """The browser's current URL from HX-Current-URL header."""
        return self.htmx.current_url

    @property
    def htmx_current_url_abs_path(self) -> str | None:
        """The path portion of the browser's current URL."""
        return self.htmx.current_url_abs_path

    @property
    def htmx_partial(self) -> str | None:
        """The partial element name from HX-Partial header (htmx 4.0+)."""
        return self.htmx.partial

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
        qs = (
            self.query._raw
            if isinstance(self.query, QueryParams)
            else object.__getattribute__(self.query, "_raw")
        )
        if qs:
            return f"{self.path}?{qs.decode('latin-1')}"
        return self.path

    # -- Async body access --

    async def body(self) -> bytes:
        """Read the full request body.

        Result is cached — the ASGI receive is consumed once, then
        the same bytes are returned on subsequent calls.
        """
        if "_body" in self._cache:
            return self._cache["_body"]
        chunks = [chunk async for chunk in self.stream()]
        result = b"".join(chunks)
        self._cache["_body"] = result
        return result

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

    async def form(self) -> FormData:
        """Parse the body as form data (URL-encoded or multipart).

        Result is cached — the body is read and parsed once, then
        the same ``FormData`` is returned on subsequent calls.

        Supports ``application/x-www-form-urlencoded`` (stdlib) and
        ``multipart/form-data`` (requires ``pip install chirp[forms]``).

        Returns:
            Parsed ``FormData`` implementing ``MultiValueMapping``.

        Raises:
            ValueError: If Content-Type is not a form encoding.
            ConfigurationError: If multipart is needed but
                ``python-multipart`` is not installed.
        """
        if "_form" in self._cache:
            return self._cache["_form"]

        from chirp.http.forms import parse_form_data

        ct = self.content_type or "application/x-www-form-urlencoded"
        raw = await self.body()
        result = await parse_form_data(raw, ct)

        # Cache in the mutable dict (frozen dataclass allows mutating
        # the dict object itself, just not replacing the field reference)
        self._cache["_form"] = result
        return result

    # -- Factory --

    @classmethod
    def from_asgi(
        cls,
        scope: Scope,
        receive: Receive,
        path_params: dict[str, str] | None = None,
    ) -> Request:
        """Create a Request from an ASGI scope and receive callable.

        Reuses request_id from scope["extensions"]["request_id"] when Pounce
        (or another ASGI server) has already set it, avoiding redundant UUID generation.
        """
        import uuid

        headers = Headers(tuple(scope.get("headers", ())))
        server = scope.get("server")
        client = scope.get("client")
        extensions = scope.get("extensions") or {}
        request_id = (
            extensions.get("request_id") or headers.get("x-request-id") or str(uuid.uuid4())
        )
        query_raw = scope.get("query_string", b"")
        cookie_header = headers.get("cookie") or ""
        return cls(
            method=scope["method"],
            path=scope["path"],
            headers=headers,
            query=_LazyQueryParams(query_raw),
            path_params=path_params or {},
            http_version=scope.get("http_version", "1.1"),
            server=tuple(server) if server else None,
            client=tuple(client) if client else None,
            cookies=_LazyCookies(cookie_header),
            request_id=request_id,
            _receive=receive,
        )

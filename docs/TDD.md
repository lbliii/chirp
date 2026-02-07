# Technical Design Document: Chirp Core Types and Protocols

**Version**: 0.2.0
**Date**: 2026-02-07
**Status**: Active (Phases 0-4 implemented)

---

## 1. Purpose

This document defines the concrete types, protocols, and interfaces that form chirp's core.
These are the building blocks that every other component depends on. Getting them right is
critical -- they're frozen (literally and figuratively) once shipped.

All code targets Python 3.14+ with free-threading support. All dataclasses use
`frozen=True, slots=True`. All type annotations use modern syntax (`X | None`, `list[str]`).

---

## 2. ASGI Type Definitions

### 2.1 Typed ASGI Scope

Chirp replaces Starlette's `Scope = MutableMapping[str, Any]` with typed scope objects.
These are internal -- users never see them.

```python
# chirp/_internal/asgi.py

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, TypeAlias

# Raw ASGI types (matching the spec)
Scope: TypeAlias = MutableMapping[str, Any]
Receive: TypeAlias = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send: TypeAlias = Callable[[MutableMapping[str, Any]], Awaitable[None]]

# Typed scope for internal use -- parsed from raw ASGI scope
@dataclass(frozen=True, slots=True)
class HTTPScope:
    type: str                           # "http"
    asgi: dict[str, str]                # {"version": "3.0"}
    http_version: str                   # "1.1" or "2"
    method: str                         # "GET", "POST", etc.
    path: str                           # "/users/42"
    raw_path: bytes                     # b"/users/42"
    query_string: bytes                 # b"q=hello&page=1"
    root_path: str                      # "" or prefix
    headers: tuple[tuple[bytes, bytes], ...]  # Raw header pairs
    server: tuple[str, int] | None      # ("localhost", 8000)
    client: tuple[str, int] | None      # ("127.0.0.1", 54321)

    @classmethod
    def from_scope(cls, scope: Scope) -> HTTPScope:
        """Parse raw ASGI scope into typed object."""
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
            server=tuple(scope["server"]) if scope.get("server") else None,
            client=tuple(scope["client"]) if scope.get("client") else None,
        )
```

---

## 3. HTTP Types

### 3.1 Headers

Immutable header collection. Case-insensitive key access.

```python
# chirp/http/headers.py

from collections.abc import Iterator, Mapping


class Headers(Mapping[str, str]):
    """Immutable, case-insensitive HTTP headers.

    Stores raw header pairs as a tuple of (name, value) byte pairs.
    Provides case-insensitive string access.
    """

    __slots__ = ("_raw", "_cache")

    def __init__(self, raw: tuple[tuple[bytes, bytes], ...] = ()) -> None:
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_cache", None)

    def __getitem__(self, key: str) -> str:
        key_lower = key.lower().encode("latin-1")
        for name, value in self._raw:
            if name.lower() == key_lower:
                return value.decode("latin-1")
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        key_lower = key.lower().encode("latin-1")
        return any(name.lower() == key_lower for name, value in self._raw)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for name, _ in self._raw:
            key = name.decode("latin-1").lower()
            if key not in seen:
                seen.add(key)
                yield key

    def __len__(self) -> int:
        return len(set(self))

    def get(self, key: str, default: str | None = None) -> str | None:
        try:
            return self[key]
        except KeyError:
            return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for a header (e.g., multiple Set-Cookie)."""
        key_lower = key.lower().encode("latin-1")
        return [
            value.decode("latin-1")
            for name, value in self._raw
            if name.lower() == key_lower
        ]

    @property
    def raw(self) -> tuple[tuple[bytes, bytes], ...]:
        """Access raw header pairs for ASGI compatibility."""
        return self._raw
```

### 3.2 QueryParams

Immutable query string parameters.

```python
# chirp/http/query.py

from urllib.parse import parse_qs
from collections.abc import Iterator, Mapping


class QueryParams(Mapping[str, str]):
    """Immutable query string parameters.

    For keys with multiple values, __getitem__ returns the first value.
    Use get_list() for all values.
    """

    __slots__ = ("_data", "_raw")

    def __init__(self, query_string: bytes = b"") -> None:
        object.__setattr__(self, "_raw", query_string)
        parsed = parse_qs(query_string.decode("latin-1"), keep_blank_values=True)
        object.__setattr__(self, "_data", parsed)

    def __getitem__(self, key: str) -> str:
        return self._data[key][0]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: str | None = None) -> str | None:
        values = self._data.get(key)
        if values:
            return values[0]
        return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for a key."""
        return list(self._data.get(key, []))

    def get_int(self, key: str, default: int | None = None) -> int | None:
        """Return value as int, or default if missing or not numeric."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool | None = None) -> bool | None:
        """Return value as bool (true/1/yes/on -> True)."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")
```

### 3.3 Request

Frozen, slotted, typed. Immutable metadata with async body access.

```python
# chirp/http/request.py

from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from typing import Any

from chirp.http.headers import Headers
from chirp.http.query import QueryParams
from chirp._internal.asgi import Receive


def _parse_cookies(header: str) -> dict[str, str]:
    """Parse a Cookie header into a dict. Pure function, no side effects."""
    if not header:
        return {}
    cookies: dict[str, str] = {}
    for pair in header.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


@dataclass(frozen=True, slots=True)
class Request:
    """An immutable HTTP request.

    Metadata (method, path, headers, etc.) is frozen at creation.
    Body is accessed asynchronously via .body(), .json(), .form().

    Cookies are parsed once at creation time (in from_asgi) and stored
    as a frozen field, not re-parsed on every .cookies access.
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
        chunks: list[bytes] = []
        async for chunk in self.stream():
            chunks.append(chunk)
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
        """Read the body as text."""
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
        return cls(
            method=scope["method"],
            path=scope["path"],
            headers=headers,
            query=QueryParams(scope.get("query_string", b"")),
            path_params=path_params or {},
            http_version=scope.get("http_version", "1.1"),
            server=tuple(scope["server"]) if scope.get("server") else None,
            client=tuple(scope["client"]) if scope.get("client") else None,
            cookies=_parse_cookies(headers.get("cookie", "")),
            _receive=receive,
        )
```

### 3.4 Response

Chainable transformations. Each `.with_*()` returns a new Response.

```python
# chirp/http/response.py

from dataclasses import dataclass, replace
from collections.abc import Mapping
from typing import Any


@dataclass(frozen=True, slots=True)
class SetCookie:
    """A Set-Cookie directive."""

    name: str
    value: str
    max_age: int | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool = False
    httponly: bool = True
    samesite: str = "lax"

    def to_header_value(self) -> str:
        """Serialize to a Set-Cookie header value."""
        parts = [f"{self.name}={self.value}"]
        if self.max_age is not None:
            parts.append(f"Max-Age={self.max_age}")
        if self.path:
            parts.append(f"Path={self.path}")
        if self.domain:
            parts.append(f"Domain={self.domain}")
        if self.secure:
            parts.append("Secure")
        if self.httponly:
            parts.append("HttpOnly")
        if self.samesite:
            parts.append(f"SameSite={self.samesite}")
        return "; ".join(parts)


@dataclass(frozen=True, slots=True)
class Response:
    """An HTTP response built through immutable transformations.

    Construct with a body, then chain .with_*() calls to set
    status, headers, and cookies. Each call returns a new Response.

    Note: No `from __future__ import annotations` needed. Python 3.14
    resolves forward references natively. SetCookie is defined above
    so the `cookies` field type is concrete at class creation time.
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
        """Return a new Response with an additional cookie."""
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
        """Return a new Response that deletes a cookie."""
        cookie = SetCookie(
            name=name,
            value="",
            max_age=0,
            path=path,
        )
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
```

---

## 4. Return Types

### 4.1 Template

```python
# chirp/templating/returns.py

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Template:
    """Render a full kida template.

    Usage:
        return Template("page.html", title="Home", items=items)
    """

    name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, /, **context: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Fragment:
    """Render a named block from a kida template.

    Usage:
        return Fragment("search.html", "results_list", results=results)
    """

    template_name: str
    block_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, template_name: str, block_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Stream:
    """Render a kida template with progressive streaming.

    Context values that are awaitables are resolved concurrently.
    Each template section streams to the browser as its data becomes available.

    Usage:
        return Stream("dashboard.html",
            header=site_header(),
            stats=await load_stats(),
            feed=await load_feed(),
        )
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, template_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)
```

### 4.2 EventStream

```python
# chirp/realtime/events.py

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """A single Server-Sent Event."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def encode(self) -> str:
        """Serialize to SSE wire format."""
        lines: list[str] = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        for line in self.data.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")  # Trailing newline
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class EventStream:
    """Stream Server-Sent Events to the client.

    The generator yields values that are converted to SSE events:
    - str: sent as data
    - dict: JSON-serialized as data
    - Fragment: rendered via kida, sent as data with event="fragment"
    - SSEEvent: sent as-is

    Usage:
        async def stream():
            async for event in bus.subscribe():
                yield Fragment("components/item.html", item=event)
        return EventStream(stream())
    """

    generator: AsyncIterator[Any]
    event_type: str | None = None
    heartbeat_interval: float = 15.0
```

---

## 5. Routing Types

### 5.1 Route

```python
# chirp/routing/route.py

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Route:
    """A frozen route definition.

    Created during app setup, compiled into the router at freeze time.
    """

    path: str
    handler: Callable[..., Any]
    methods: frozenset[str]
    name: str | None = None


@dataclass(frozen=True, slots=True)
class RouteMatch:
    """Result of a successful route match."""

    route: Route
    path_params: dict[str, str]


@dataclass(frozen=True, slots=True)
class PathSegment:
    """A parsed segment of a route path."""

    # Static: "/users"
    # Param:  "/{id}"
    # Param with type: "/{id:int}"
    value: str
    is_param: bool = False
    param_name: str | None = None
    param_type: str = "str"  # "str", "int", "float", "path"
```

### 5.2 Parameter Converters

```python
# chirp/routing/params.py

from typing import Any


# Built-in type converters for path parameters
CONVERTERS: dict[str, tuple[str, type]] = {
    "str":   (r"[^/]+",  str),
    "int":   (r"\d+",    int),
    "float": (r"\d+(?:\.\d+)?", float),
    "path":  (r".+",     str),
}


def convert_param(value: str, param_type: str) -> Any:
    """Convert a path parameter string to the specified type.

    Raises ValueError if conversion fails.
    """
    _, target_type = CONVERTERS[param_type]
    return target_type(value)
```

---

## 6. Middleware Protocol

```python
# chirp/middleware/protocol.py

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeAlias

from chirp.http.request import Request
from chirp.http.response import Response

# The next handler in the middleware chain
Next: TypeAlias = Callable[[Request], Awaitable[Response]]


class Middleware(Protocol):
    """Protocol for chirp middleware.

    Accepts both functions and callable objects:

        # Function middleware
        async def my_middleware(request: Request, next: Next) -> Response:
            response = await next(request)
            return response.with_header("X-Custom", "value")

        # Class middleware
        class MyMiddleware:
            async def __call__(self, request: Request, next: Next) -> Response:
                response = await next(request)
                return response.with_header("X-Custom", "value")
    """

    async def __call__(self, request: Request, next: Next) -> Response: ...
```

---

## 7. Configuration

```python
# chirp/config.py

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration. Immutable after creation.

    All fields have sensible defaults. Override what you need.
    """

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # Security
    secret_key: str = ""

    # Templates
    template_dir: str | Path = "templates"
    autoescape: bool = True

    # Static files
    static_dir: str | Path | None = "static"
    static_url: str = "/static"

    # SSE
    sse_heartbeat_interval: float = 15.0

    # Limits
    max_content_length: int = 16 * 1024 * 1024  # 16MB
```

---

## 8. App Interface

```python
# chirp/app.py (interface sketch -- not full implementation)

import threading
from collections.abc import Callable
from typing import Any

from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import Middleware
from chirp._internal.asgi import Scope, Receive, Send


class App:
    """The chirp application.

    Mutable during setup (route registration, middleware, filters).
    Frozen at runtime when app.run() or __call__() is first invoked.

    Thread safety:
        The setup phase is single-threaded (decorators at import time).
        The freeze transition uses a Lock + double-check to ensure exactly
        one thread compiles the app, even under free-threading where
        multiple ASGI workers could call __call__() concurrently on
        first request.
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config: AppConfig = config or AppConfig()
        self._routes: list[_PendingRoute] = []
        self._middleware: list[Middleware] = []
        self._error_handlers: dict[int | type, Callable[..., Any]] = {}
        self._template_filters: dict[str, Callable[..., Any]] = {}
        self._template_globals: dict[str, Any] = {}
        self._frozen: bool = False
        self._freeze_lock: threading.Lock = threading.Lock()

    # -- Route registration --

    def route(
        self,
        path: str,
        *,
        methods: list[str] | None = None,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a route handler."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            self._routes.append(_PendingRoute(path, func, methods, name))
            return func
        return decorator

    # -- Error handlers --

    def error(
        self, code_or_exception: int | type[Exception],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an error handler."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            self._error_handlers[code_or_exception] = func
            return func
        return decorator

    # -- Middleware --

    def add_middleware(self, middleware: Middleware) -> None:
        """Add a middleware to the pipeline."""
        self._check_not_frozen()
        self._middleware.append(middleware)

    # -- Template integration --

    def template_filter(
        self, name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a kida template filter."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            filter_name = name or func.__name__
            self._template_filters[filter_name] = func
            return func
        return decorator

    def template_global(
        self, name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a kida template global."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            global_name = name or func.__name__
            self._template_globals[global_name] = func
            return func
        return decorator

    # -- Lifecycle --

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Start the development server.

        Compiles the app (freezing routes, middleware, templates)
        and starts serving requests.
        """
        self._ensure_frozen()
        # ... start dev server ...

    # -- ASGI interface --

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 3.0 entry point."""
        self._ensure_frozen()
        # ... handle request ...

    # -- Internal --

    def _ensure_frozen(self) -> None:
        """Thread-safe freeze with double-check locking.

        Under free-threading (3.14t), multiple ASGI worker threads could
        call __call__() concurrently on first request. This pattern ensures
        exactly one thread performs compilation:

        1. Fast path: if already frozen, return immediately (no lock)
        2. Slow path: acquire lock, check again, freeze if still needed
        """
        if self._frozen:
            return
        with self._freeze_lock:
            if self._frozen:
                return
            self._freeze()

    def _freeze(self) -> None:
        """Compile the app into its frozen runtime state.

        MUST only be called while holding _freeze_lock.
        """
        # 1. Compile route table
        # 2. Build middleware chain (captured as tuple)
        # 3. Initialize kida environment
        # 4. Validate configuration
        self._frozen = True

    def _check_not_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(
                "Cannot modify the app after it has started serving requests. "
                "Register routes, middleware, and filters before calling app.run()."
            )
```

---

## 9. Content Negotiation

```python
# chirp/server/negotiation.py (interface sketch)

from typing import Any

from chirp.http.response import Response, Redirect
from chirp.templating.returns import Template, Fragment, Stream
from chirp.realtime.events import EventStream


def negotiate(value: Any) -> Response | StreamingResponse | SSEResponse:
    """Convert a route handler's return value to a Response.

    Dispatch order:
    1. Response         -> pass through
    2. Redirect         -> Response with Location header
    3. Template         -> render via kida -> Response
    4. Fragment         -> render block via kida -> Response
    5. Stream           -> streaming kida render -> StreamingResponse
    6. EventStream      -> SSE response -> SSEResponse
    7. str              -> Response(text/html)
    8. bytes            -> Response(application/octet-stream)
    9. dict / list      -> JSON serialize -> Response(application/json)
    10. tuple(value, int)           -> negotiate value, override status
    11. tuple(value, int, dict)     -> negotiate value, override status + headers
    """
    match value:
        case Response():
            return value
        case Redirect():
            return (
                Response(body="")
                .with_status(value.status)
                .with_header("Location", value.url)
            )
        case Template():
            html = _render_template(value)
            return Response(body=html)
        case Fragment():
            html = _render_fragment(value)
            return Response(body=html)
        case Stream():
            return _create_streaming_response(value)
        case EventStream():
            return _create_sse_response(value)
        case str():
            return Response(body=value)
        case bytes():
            return Response(
                body=value,
                content_type="application/octet-stream",
            )
        case dict() | list():
            import json
            return Response(
                body=json.dumps(value, default=str),
                content_type="application/json; charset=utf-8",
            )
        case (inner, int() as status):
            response = negotiate(inner)
            return response.with_status(status)
        case (inner, int() as status, dict() as headers):
            response = negotiate(inner)
            return response.with_status(status).with_headers(headers)
        case _:
            raise TypeError(
                f"Cannot convert {type(value).__name__} to a response. "
                f"Return str, dict, bytes, Template, Fragment, Stream, "
                f"EventStream, Response, or Redirect."
            )
```

---

## 10. Public API Surface

Everything users need is re-exported from `chirp.__init__`:

```python
# chirp/__init__.py

# App
from chirp.app import App
from chirp.config import AppConfig

# HTTP
from chirp.http.request import Request
from chirp.http.response import Response, Redirect

# Templates
from chirp.templating.returns import Template, Fragment, Stream

# Real-time
from chirp.realtime.events import EventStream, SSEEvent

# Middleware
from chirp.middleware.protocol import Middleware, Next

# Context
from chirp.context import get_request, g

__all__ = [
    # App
    "App",
    "AppConfig",
    # HTTP
    "Request",
    "Response",
    "Redirect",
    # Templates
    "Template",
    "Fragment",
    "Stream",
    # Real-time
    "EventStream",
    "SSEEvent",
    # Middleware
    "Middleware",
    "Next",
    # Context
    "get_request",
    "g",
]
```

**Built-in middleware (separate imports):**

```python
from chirp.middleware import CORSMiddleware, CORSConfig, StaticFiles
from chirp.middleware.sessions import SessionMiddleware, SessionConfig, get_session
```

**Minimal import for hello world:**

```python
from chirp import App
```

**Full import for a real application:**

```python
from chirp import App, AppConfig, Request, Template, Fragment, EventStream, g
```

---

## 11. Testing Interface

```python
# chirp/testing.py (interface sketch)

from chirp.app import App
from chirp.http.request import Request
from chirp.http.response import Response


class TestClient:
    """Async test client for chirp applications.

    Returns the same Response type used in production.

    Usage:
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
    """

    def __init__(self, app: App) -> None:
        self.app = app

    async def __aenter__(self) -> TestClient:
        if not self.app._frozen:
            self.app._freeze()
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ) -> Response:
        """Send a GET request."""
        ...

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        data: dict[str, str] | None = None,
    ) -> Response:
        """Send a POST request."""
        ...

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send an arbitrary request."""
        ...

    # -- Fragment helpers --

    async def fragment(
        self,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send a fragment request (sets HX-Request header)."""
        fragment_headers = {"HX-Request": "true"}
        if headers:
            fragment_headers.update(headers)
        return await self.request(method, path, headers=fragment_headers)
```

---

## 12. File Inventory

Summary of all files to be created for Phase 0 (Foundation):

```
chirp/
├── __init__.py              # Public API re-exports
├── py.typed                 # PEP 561 marker
├── app.py                   # App class (setup + freeze + ASGI)
├── config.py                # AppConfig frozen dataclass
├── context.py               # Request-scoped ContextVar (request_var, g namespace)
├── http/
│   ├── __init__.py          # Re-export Request, Response, etc.
│   ├── request.py           # Request frozen dataclass
│   ├── response.py          # Response + SetCookie + Redirect
│   ├── headers.py           # Immutable Headers mapping
│   ├── query.py             # Immutable QueryParams mapping
│   └── cookies.py           # Cookie parsing utilities
├── routing/
│   ├── __init__.py
│   ├── route.py             # Route, RouteMatch, PathSegment
│   ├── router.py            # Router with compile + match
│   └── params.py            # Path parameter converters
├── middleware/
│   ├── __init__.py          # Re-export protocols + built-in middleware
│   ├── protocol.py          # Middleware Protocol + Next type
│   ├── builtin.py           # CORSMiddleware + CORSConfig
│   ├── static.py            # StaticFiles middleware
│   └── sessions.py          # SessionMiddleware + SessionConfig + get_session
├── templating/
│   ├── __init__.py
│   └── returns.py           # Template, Fragment, Stream
├── realtime/
│   ├── __init__.py
│   └── events.py            # EventStream, SSEEvent
├── server/
│   ├── __init__.py
│   ├── handler.py           # ASGI request handler (dispatch + error handling)
│   └── negotiation.py       # Content negotiation dispatch
├── testing.py               # TestClient
└── _internal/
    ├── __init__.py
    ├── asgi.py              # Typed ASGI definitions
    └── multimap.py          # MultiValueMapping protocol
```

---

## 13. Kida Integration Requirements

The following kida capabilities are needed. Verified against kida v0.1.2 (2026-02-07).

| Capability | Kida Status | Chirp Phase | Chirp Status |
|------------|-------------|-------------|--------------|
| `Environment(loader=...)` | Exists | Phase 2 | ✅ Integrated |
| `env.get_template(name)` | Exists | Phase 2 | ✅ Integrated |
| `template.render(**ctx)` | Exists | Phase 2 | ✅ Integrated |
| `template.render_async(**ctx)` | Exists (wraps render in `asyncio.to_thread`) | Phase 2 | Not yet used |
| `env.update_filters(dict)` | Exists | Phase 2 | ✅ Integrated |
| `env.add_global(name, value)` | Exists | Phase 2 | ✅ Integrated |
| `template.render_block(name, **ctx)` | **Exists** | Phase 3 | ✅ Integrated |
| `template.list_blocks()` | **Exists** | Phase 3 | Available (not yet exposed to user API) |
| `template.render_stream(**ctx)` | **Not implemented** (stub `RenderedTemplate` class exists) | Phase 5 | Blocked on kida |

### render_block — Integrated

Kida compiles each `{% block %}` as an independent `_block_{name}(ctx, _blocks)` function in
the template namespace. `template.render_block("results_list", **ctx)` renders just that block
without the full template. `template.list_blocks()` returns available block names.

**Location:** `kida/template/core.py:436-501`

**Important semantic:** `render_block()` and `list_blocks()` only expose blocks that the
template itself defines or overrides. Blocks inherited from a parent template (via
`{% extends %}`) that are not overridden are *not* available. This is by design -- the child
template only "owns" what it explicitly declares.

Chirp's `Fragment` return type uses `render_block()` via `templating/integration.py`. Contract
tests for `render_block()` and `list_blocks()` are in the kida repo (`tests/test_render_block.py`,
12 tests).

### render_stream — Requires Kida Work

Kida uses a StringBuilder pattern (`buf.append()` + `''.join(buf)`) which accumulates all
output before returning. A `RenderedTemplate` stub class exists (`kida/template/core.py:629-650`)
but currently just yields the full string.

To support chirp's `Stream` return type, kida needs:
1. A generator-based rendering path (yield at block boundaries)
2. A `render_stream()` method on Template returning an iterator of chunks
3. The compiler to support generating yield-based render functions

This is the only kida dependency that blocks a chirp phase. Plan as parallel work alongside
chirp Phases 2-4, targeting completion before Phase 5.

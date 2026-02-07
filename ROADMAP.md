# Chirp

**A Python web framework for the modern web platform.**

Chirp is a web framework built for Python 3.14t that serves HTML beautifully -- full pages,
fragments, streams, and real-time events -- all through its built-in template engine, kida.

Named after the distinctive vocalization of the Bengal cat, chirp is part of a family of
Python tools: **bengal** (static site generator), **kida** (template engine), **patitas**
(markdown parser), and **rosettes** (syntax highlighter).

---

## Why Chirp Exists

Flask (2010) and FastAPI (2018) were designed for a different web. Flask assumes you render
full HTML pages or bolt on extensions for everything. FastAPI assumes you serve JSON to a
JavaScript frontend. Neither reflects where the web platform is in 2026:

- The browser has `<dialog>`, `popover`, View Transitions, container queries, CSS nesting,
  and anchor positioning. Most of what required a JS framework is now native HTML and CSS.
- htmx proved that servers can send HTML fragments and the browser can swap them in --
  partial page updates with no custom JavaScript.
- Streaming HTML lets the server send the page shell immediately and fill in content as
  data becomes available. No loading spinners, no skeleton screens.
- Server-Sent Events push real-time updates over plain HTTP. No WebSocket protocol upgrade,
  no special infrastructure.

No Python framework is built around these capabilities. Flask and Django treat templates as
"render a full page, return a string." FastAPI doesn't have a template story at all. None of
them can render a template *block* as a fragment. None of them stream HTML as it renders.
None of them have first-class SSE support for pushing HTML updates.

Chirp is designed from scratch for this reality.

---

## Design Principles

These are distilled from building bengal, kida, patitas, and rosettes -- not as rigid rules,
but as consistent instincts that shape every decision.

### 1. The obvious thing should be the easy thing

`highlight("code", "python")`. `parse("# Hello")`. `env.render_string("{{ x }}", x=1)`.
You never make someone understand the system to use the system. The simple call works. The
architecture reveals itself only when you need it.

### 2. Data should be honest about what it is

If something doesn't change after creation, it shouldn't pretend it might. If something is
built incrementally, it should be honest about that too. Don't force immutability where the
shape of the problem is mutable -- match the tool to the truth.

### 3. Extension should be structural, not ceremonial

Never make someone inherit from a base class just to participate. If a thing quacks like a
middleware, it *is* a middleware. The system discovers capability from shape, not from lineage.

### 4. The system should be transparent

No proxies hiding `type: ignore`. No magic globals. No "it works but don't look at how."
If someone reads the code, the flow is traceable from entry to exit.

### 5. Own what matters, delegate what doesn't

Own the interface, own the developer experience, own the hot path. Delegate the commodity
infrastructure. Write the template engine (kida) because templates are the thing. Use anyio
for the async runtime because writing your own is insane.

---

## Architecture

### Module Layout

```
chirp/
├── __init__.py              # Public API: App, Request, Response, Template, Fragment, ...
├── app.py                   # App class -- decorator setup, frozen at runtime
├── config.py                # AppConfig -- frozen dataclass
├── routing/
│   ├── __init__.py
│   ├── router.py            # Compiled route table with O(1)-ish matching
│   ├── route.py             # Route definition (path, methods, handler)
│   └── params.py            # Path parameter parsing and conversion
├── http/
│   ├── __init__.py
│   ├── request.py           # Request -- frozen, slotted, typed
│   ├── response.py          # Response -- chainable .with_*() API
│   ├── headers.py           # Immutable Headers with mutable builder
│   └── cookies.py           # Cookie handling
├── middleware/
│   ├── __init__.py
│   ├── protocol.py          # Middleware Protocol definition
│   └── builtin.py           # CORS, error handling, static files
├── templating/
│   ├── __init__.py
│   ├── integration.py       # Kida environment setup and app binding
│   ├── returns.py           # Template, Fragment, Stream return types
│   └── filters.py           # App-registered template filters
├── realtime/
│   ├── __init__.py
│   ├── sse.py               # Server-Sent Events support
│   └── events.py            # EventStream return type
├── server/
│   ├── __init__.py
│   ├── handler.py           # ASGI handler -- translates ASGI ↔ chirp types
│   └── dev.py               # Development server with hot reload
└── _internal/
    ├── __init__.py
    └── asgi.py              # Raw ASGI type definitions (typed, not Any)
```

### Core Abstractions

```
┌─────────────────────────────────────────────────────────┐
│  Surface Layer -- What developers touch                 │
│                                                         │
│  App          @app.route()      AppConfig               │
│  Template     Fragment          Stream                  │
│  EventStream  Response          Redirect                │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  Core Layer -- Typed, immutable where honest            │
│                                                         │
│  Request (frozen, slots)    Router (compiled)            │
│  Response (.with_*() chain) Middleware (Protocol)        │
│  Headers (immutable)        Route (frozen)               │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  Engine Layer -- ASGI + integrations                    │
│                                                         │
│  ASGI handler        Kida environment                   │
│  Dev server          SSE handler                        │
│  anyio runtime                                          │
└─────────────────────────────────────────────────────────┘
```

---

## The App

Decorators during setup, frozen at runtime. Routes are registered with `@app.route()` because
that's ergonomic and everyone knows it. When `app.run()` is called, the route table compiles
and the app becomes effectively immutable. No more registration, no runtime mutation.

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

@app.route("/users/{id}")
def user(id: int):
    return {"id": id, "name": "..."}

app.run()
```

Five lines to hello world. Flask-familiar on the surface -- because Flask got the surface right.

### Configuration

```python
from chirp import App, AppConfig

config = AppConfig(
    debug=True,
    host="0.0.0.0",
    port=8000,
    secret_key="...",
    template_dir="templates/",
)
app = App(config=config)
```

`AppConfig` is `@dataclass(frozen=True, slots=True)`. Every field has IDE autocomplete. No
string-key dict, no runtime `KeyError`, no `app.config["SCRET_KEY"]` typos.

---

## Return Values, Not Response Construction

Route functions return *values*. The framework handles content negotiation based on the type:

```python
return "Hello"                                  # -> 200, text/html
return {"users": [...]}                         # -> 200, application/json
return Template("page.html", title="Home")      # -> 200, rendered via kida
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)    # -> 200, streamed HTML
return EventStream(generator())                 # -> SSE stream
return Response(body=b"...", status=201)         # -> explicit control
return Redirect("/login")                       # -> 302
```

No `make_response()`. No `jsonify()`. The type *is* the intent.

---

## The Request: Actually Immutable

A request is received data. From the handler's perspective, it doesn't change. The object
should be honest about that.

```python
@app.route("/search")
async def search(request: Request):
    q = request.query.get("q", "")
    # request.headers, request.path, request.method -- all immutable
    # request.body() / request.json() / request.form() -- async, lazy
    return {"results": [...]}
```

`@dataclass(frozen=True, slots=True)` for metadata. Async methods for body access. Typed
attributes with IDE completion. No `request.environ` dict bag.

### Fragment-Aware Requests

```python
@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query["q"])
    if request.is_fragment:  # HX-Request header detected
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```

The request knows whether it came from htmx or a full page navigation. The handler returns
the appropriate response -- a fragment or a full page -- through the same template.

---

## The Response: Chainable, Not Mutable, Not Frozen

Responses are built through transformation. Each `.with_*()` returns a new Response.

```python
return (
    Response("Created")
    .with_status(201)
    .with_header("Location", "/users/42")
    .with_cookie("session", token)
)
```

Immutable transformations, chainable API. This is honest about the shape: responses are built
incrementally but shouldn't be mutated after they're sent. No `response.headers["X-Foo"] = "bar"`
mutation.

---

## Middleware: Just a Function With a Shape

No base class. No inheritance. A middleware is anything that matches the protocol:

```python
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    return response.with_header("X-Time", f"{elapsed:.3f}")

app.add_middleware(timing)
```

A function that takes a request and a `next`, returns a response. If you want a class with
state, write a class with `__call__`. The framework checks the shape, not the lineage.

```python
class RateLimiter:
    def __init__(self, max_requests: int, window: float) -> None:
        self.max_requests = max_requests
        self.window = window

    async def __call__(self, request: Request, next: Next) -> Response:
        # ... rate limiting logic ...
        return await next(request)

app.add_middleware(RateLimiter(max_requests=100, window=60.0))
```

Both work. The `Middleware` protocol accepts either.

---

## Kida Integration: Not a Dependency, a Feature

Kida isn't "the template engine you can swap out." It's a built-in capability, like JSON
serialization. Same author, same standards, same type safety. The seam between framework
and template engine disappears.

```python
@app.route("/")
def index():
    return Template("index.html", title="Home", items=items)

@app.template_filter()
def currency(value: float) -> str:
    return f"${value:,.2f}"

@app.template_global()
def site_name() -> str:
    return "My App"
```

### Fragment Rendering

This is chirp's key innovation. Kida can render a named block from a template independently,
without rendering the whole page:

```html
{# templates/search.html #}
{% extends "base.html" %}

{% block content %}
  <input type="search" hx-get="/search" hx-target="#results" name="q">
  {% block results_list %}
    <div id="results">
      {% for item in results %}
        <div class="result">{{ item.title }}</div>
      {% endfor %}
    </div>
  {% endblock %}
{% endblock %}
```

```python
@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query.get("q", ""))
    if request.is_fragment:
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```

Full page request renders everything. htmx request renders just the `results_list` block.
Same template, same data, different scope. No separate "partials" directory. No duplicated
markup.

### Streaming HTML

Kida renders template sections as they complete. The browser receives the shell immediately
and content fills in progressively:

```python
@app.route("/dashboard")
async def dashboard(request: Request):
    return Stream("dashboard.html",
        header=site_header(),               # sends immediately
        stats=await load_stats(),           # streams when ready
        activity=await load_activity(),     # streams when ready
    )
```

No JavaScript loading states. The HTTP response itself is chunked. The browser renders
progressively as chunks arrive.

### Server-Sent Events

Push kida-rendered HTML fragments to the browser in real-time:

```python
@app.route("/notifications")
async def notifications(request: Request):
    async def stream():
        async for event in notification_bus.subscribe(request.user):
            yield Fragment("components/notification.html", event=event)
    return EventStream(stream())
```

Combined with htmx's SSE support, this enables real-time UI updates with zero client-side
JavaScript. The server renders HTML, the browser swaps it in.

---

## Free-Threading: By Architecture, Not by Testing

Chirp doesn't "pass tests on 3.14t." It makes data races structurally impossible.

- **ContextVar** for request scope (like patitas' ParseConfig pattern)
- **Route table** compiles to an immutable structure at startup
- **Response chain** produces new objects, never mutates
- **Request** is frozen
- **Config** is frozen
- **No module-level mutable state**
- **`_Py_mod_gil = 0`** declared

The framework is designed for free-threading from the first line of code, not adapted to it
after the fact.

---

## Dependencies

### Core (minimal)

```
chirp (the framework)
├── kida          # template engine -- same ecosystem, same author
└── anyio         # async runtime -- good, minimal, not worth rewriting
```

### Optional (explicit extras)

```
pip install chirp[forms]      # python-multipart -- form/multipart parsing
pip install chirp[sessions]   # itsdangerous -- signed session cookies
pip install chirp[testing]    # httpx -- test client
```

Own the developer interface. Delegate the async runtime. Delegate security-critical parsing
to battle-tested libraries. Never vendor, never rewrite what doesn't need rewriting.

---

## Error Handling

Decorator-based error handlers, consistent with the route registration pattern:

```python
@app.error(404)
def not_found(request: Request):
    return Template("errors/404.html", path=request.path)

@app.error(500)
def server_error(request: Request, error: Exception):
    return Template("errors/500.html", error=str(error))

@app.error(ValidationError)
def validation_error(request: Request, error: ValidationError):
    return Response(str(error)).with_status(422)
```

Errors are handled through the same return-value system. Return a `Template`, a `Response`,
a string, a dict -- the framework handles it the same way as any route.

---

## Testing

The test client uses the same `Request` and `Response` types as production. No wrapper
translation layer.

```python
from chirp.testing import TestClient

async def test_homepage():
    async with TestClient(app) as client:
        response = await client.get("/")
        assert response.status == 200
        assert "Hello" in response.text

async def test_fragment():
    async with TestClient(app) as client:
        response = await client.get("/search?q=test", headers={"HX-Request": "true"})
        assert response.status == 200
        assert "<div id=\"results\">" in response.text
        # No full page wrapper -- just the fragment
        assert "<html>" not in response.text
```

---

## Phased Roadmap

### Phase 0: Foundation ✅

Establish the project structure, tooling, and core abstractions.

- [x] Project scaffolding: `pyproject.toml`, ruff, ty, test infrastructure
- [x] `AppConfig` frozen dataclass
- [x] `Request` frozen dataclass with typed attributes
- [x] `Response` with `.with_*()` chainable API
- [x] Immutable `Headers` and `QueryParams`
- [x] Path parameter parsing and type conversion

Additional primitives built during foundation:
- [x] `MultiValueMapping` protocol (shared by Headers, QueryParams, future FormData)
- [x] Error hierarchy: `ChirpError`, `HTTPError`, `NotFound`, `MethodNotAllowed`, `ConfigurationError`
- [x] Cookie consolidation: `parse_cookies()` + `SetCookie` in one module
- [x] `Handler` and `ErrorHandler` type aliases
- [x] `HTTPScope` typed ASGI dataclass

### Phase 1: Routing and App ✅

The minimal "hello world" works.

- [x] Route definition and registration via `@app.route()`
- [x] Compiled route table (freeze on `app.run()`)
- [x] Return-value content negotiation (str, dict, Response, Redirect, tuples)
- [x] ASGI handler translating between ASGI scope/messages and chirp types
- [x] Basic error handling with `@app.error()`
- [x] Development server with auto-reload via pounce ASGI server (`server/dev.py`)

Additional work completed:
- [x] Trie-based router with static, parameterized, and catch-all path matching
- [x] Handler signature introspection for automatic Request + path param injection
- [x] Thread-safe `App._freeze()` with double-check locking for free-threading

### Phase 2: Kida Integration ✅

Templates become a first-class return type.

- [x] Kida environment setup bound to app (`templating/integration.py`)
- [x] `Template` return type renders via kida
- [x] `Fragment` return type renders named blocks via kida `render_block()`
- [x] `@app.template_filter()` and `@app.template_global()` decorators
- [x] Template auto-reload in debug mode (`auto_reload=config.debug` passed to kida Environment)

Implementation notes:
- Kida `Environment` is created once during `App._freeze()` and threaded through
  the request pipeline via explicit parameters (no globals, no ContextVar)
- `render_block()` only sees blocks the template explicitly defines or overrides --
  inherited parent blocks that aren't overridden are not available via Fragment
- Contract tests for `render_block()` and `list_blocks()` added to kida repo (12 tests)

### Phase 3: Fragments and htmx ✅

The key differentiator lands.

- [x] `Fragment` return type -- render a named block from a template
- [x] `request.is_fragment` detection (HX-Request header)
- [x] Fragment-aware error handling (htmx errors return `<div class="chirp-error">` snippets)
- [x] Kida block-level rendering integration (kida `render_block()` verified available in v0.1.2)

Additional htmx detection:
- [x] `request.htmx_target` -- HX-Target header
- [x] `request.htmx_trigger` -- HX-Trigger header

### Phase 4: Middleware and Sessions ✅

The framework becomes usable for real applications.

- [x] `Middleware` protocol definition
- [x] Middleware pipeline execution
- [x] Built-in CORS middleware (`CORSMiddleware` with `CORSConfig`)
- [x] Built-in static file serving (`StaticFiles` with path traversal protection)
- [x] Session middleware (signed cookies via optional `itsdangerous`)
- [x] Request-scoped user context via ContextVar (`request_var`, `g` namespace)

Implementation notes:
- Error handlers now receive `(request, exception)` via signature introspection (backward-compatible
  with zero-arg handlers). Supports both sync and async error handlers.
- `g` is a mutable per-request namespace backed by ContextVar, reset after each request.
- `CORSMiddleware` handles preflight OPTIONS, credentials, expose-headers, multiple origins.
- `StaticFiles` resolves paths and checks `is_relative_to()` to prevent traversal.
- `SessionMiddleware` requires `itsdangerous` (optional dep). Raises `ConfigurationError` if missing.
  Session data is JSON-serialized into a signed cookie with sliding expiration.

### Phase 5: Streaming HTML ✅

Progressive page rendering.

- [x] `Stream` return type defined
- [x] Chunked transfer encoding in ASGI handler (`_send_streaming_response` in `handler.py`)
- [x] Kida streaming renderer (`render_stream()` implemented -- dual-mode compiler generates both StringBuilder and generator functions)
- [x] `StreamingResponse` dataclass with chainable `.with_*()` methods for middleware compatibility
- [x] Content negotiation wires `Stream` → kida `render_stream()` → chunked ASGI
- [x] Mid-stream error handling (HTML comment injection + graceful stream close)

Implementation notes:
- Kida's compiler now generates both `render()` (StringBuilder) and `render_stream()` (generator) from each template in a single compilation pass. No performance impact on `render()`.
- `StreamingResponse` is a peer to `Response` with the same chainable API (`with_status`, `with_header`, `with_headers`, `with_content_type`) using `dataclasses.replace` for immutability.
- Middleware protocol updated: `Next` returns `AnyResponse = Response | StreamingResponse | SSEResponse`.

### Phase 6: Real-Time ✅

Server-Sent Events for live HTML updates.

- [x] `EventStream` return type defined
- [x] `SSEEvent` with wire-format `encode()` method
- [x] SSE protocol implementation over ASGI (`handle_sse` in `realtime/sse.py`)
- [x] Fragment rendering in SSE events (kida `Fragment` → render via kida env → SSE data frame)
- [x] Connection lifecycle management (event producer task, disconnect monitor, heartbeat on idle)
- [x] `SSEResponse` dataclass with no-op `.with_*()` methods (SSE headers are fixed by protocol)
- [x] Content negotiation wires `EventStream` → `SSEResponse` → `handle_sse` dispatch

Implementation notes:
- SSE handler launches two concurrent tasks: an event producer (consumes `EventStream.generator`, formats events, sends as ASGI body chunks) and a disconnect monitor (waits for `http.disconnect`, cancels producer).
- `_format_event()` handles `SSEEvent`, `Fragment` (rendered via kida), `str`, and `dict` (JSON-serialized) types.
- Heartbeat comments (`: heartbeat`) sent when idle via `asyncio.shield` + `wait_for`
  pattern. Each `__anext__()` call is wrapped in a shielded task so that heartbeat
  timeouts don't cancel the pending generator coroutine.

### Phase 7: Testing and Polish

Production readiness.

- [x] `TestClient` with async context manager
- [x] `TestClient.fragment()` method for htmx testing
- [x] Fragment assertion helpers
- [x] SSE testing utilities
- [x] Comprehensive error messages
- [ ] Documentation site (built with bengal, naturally)

Implementation notes:
- Fragment assertion helpers (`assert_is_fragment`, `assert_fragment_contains`,
  `assert_fragment_not_contains`, `assert_is_error_fragment`) added to `testing.py`
  as standalone functions. Tests use these instead of raw string assertions.
- `TestClient.sse()` method connects to SSE endpoints, collects structured `SSEEvent`
  objects into an `SSETestResult`. Supports `max_events` (event-count disconnect) and
  `disconnect_after` (time-based disconnect). Uses `asyncio.sleep(0)` in the send
  callback to yield control when the producer loop would otherwise starve the event loop.
- SSE integration testing revealed a bug: `produce_events()` in `realtime/sse.py` had a
  `next_event_with_heartbeat()` helper that was defined but never called (dead code).
  Replaced with `asyncio.shield` + `wait_for` pattern that sends heartbeat comments on
  idle without cancelling the pending generator coroutine.
- `MethodNotAllowed` detail now includes allowed methods in the message body, not just
  the `Allow` header. Router `NotFound` includes the HTTP method in the detail string.
- `negotiation.py` raises `ConfigurationError` (from the error hierarchy) instead of
  bare `RuntimeError` for missing kida integration.
- Error types (`ChirpError`, `HTTPError`, `NotFound`, `MethodNotAllowed`,
  `ConfigurationError`) exported from `chirp.__init__` for discoverability.

---

## Non-Goals

Chirp deliberately does not:

- **Include an ORM.** Database access is your choice. Chirp serves HTML.
- **Include an admin panel.** Build it yourself with chirp's own tools.
- **Include a full auth framework.** Chirp provides middleware protocols and session
  support. Authentication logic is yours.
- **Generate OpenAPI specs.** Chirp is an HTML-over-the-wire framework, not a JSON API
  framework. If you need OpenAPI, use FastAPI.
- **Support WSGI.** Chirp is ASGI-only. Synchronous Python is not the future.
- **Compete with Django.** If you need auth, admin, ORM, email, and background jobs by
  next Tuesday, use Django. Chirp is for people who want to own their stack.
- **Abstract away the web platform.** Chirp embraces HTML, CSS, and the browser's native
  APIs. It doesn't replace them with a component framework.

---

## The Stack

Chirp is part of a cohesive ecosystem:

```
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

Each tool is independent. Together they form a complete web platform, built for Python 3.14t,
with zero external dependencies at the library level.

---

*Chirp: because bengals don't bark.*

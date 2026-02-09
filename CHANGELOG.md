# Changelog

All notable changes to chirp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-02-09

Initial release of Chirp — a Python web framework for HTML-over-the-wire apps,
built for Python 3.14t with free-threading support.

### Added

#### Core Framework

- `App` — ASGI application with route registration, middleware pipeline, and
  lifecycle management
- `AppConfig` — Frozen configuration with sensible defaults
- Type-driven content negotiation: return strings, dicts, `Template`, `Fragment`,
  `Stream`, `EventStream`, `Response`, or `Redirect` from route handlers

#### Routing

- Decorator-based route registration with `@app.route(path)`
- Path parameters with type conversion (`/users/{id:int}`)
- Method dispatch (`GET`, `POST`, `PUT`, `DELETE`, etc.)
- Automatic `HEAD` and `OPTIONS` handling

#### Templates (Kida Integration)

- `Template(name, **ctx)` — Full-page Kida template rendering
- `Fragment(name, block, **ctx)` — Render named template blocks independently
  for htmx partial updates
- `Stream(name, **ctx)` — Progressive HTML streaming via Kida
- Auto-discovery of template directories

#### Real-Time

- `EventStream(generator)` — Server-Sent Events for real-time HTML updates
- SSE with Kida-rendered fragments for zero-JS real-time UI

#### HTTP

- Immutable `Request` with query params, headers, cookies, body parsing
- Chainable `Response` with `with_header()`, `with_cookie()` methods
- `Redirect` for HTTP redirects
- `form_from()` for typed form binding and validation

#### Middleware

- Protocol-based middleware (`async def mw(request, next) -> Response`)
- Built-in: CORS, StaticFiles, HTMLInject, Sessions
- `app.add_middleware()` for composable request/response pipelines

#### Security

- Session middleware with signed cookies (via itsdangerous)
- `login()`, `logout()`, `get_user()` authentication helpers
- `@login_required` and `@requires()` authorization decorators
- `is_safe_url()` for open redirect protection

#### Data

- `Database` — Typed async database access (SQLite via aiosqlite, PostgreSQL
  via asyncpg)

#### AI

- `LLM` — Provider-agnostic LLM streaming via raw HTTP
- `ToolCallEvent` for structured tool calling

#### Testing

- `TestClient` — HTTPX-based test client for isolated route testing

#### Developer Experience

- `app.run()` — Built-in development server via Pounce
- `app.check()` — Compile-time validation of the full hypermedia surface
  (routes, template refs, fragment blocks)
- `py.typed` PEP 561 marker for type checker support
- Free-threading declaration (`_Py_mod_gil = 0`)

### Dependencies

- `kida-templates>=0.1.2` — Template engine
- `anyio>=4.0` — Async runtime
- `bengal-pounce>=0.1.0` — ASGI server

[0.1.0]: https://github.com/lbliii/chirp/releases/tag/v0.1.0

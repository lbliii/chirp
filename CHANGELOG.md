# Changelog

All notable changes to chirp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] — 2026-02-18

### Added

- **Islands (V1)** — Framework-agnostic contract for isolated high-state UI widgets:
  - Mount metadata: `data-island`, `data-island-props`, `data-island-src`, `data-island-version`, `data-island-primitive`
  - `app.check()` validates island mounts and primitive contracts
  - No-build primitive style: plain ES modules from `/static/islands/*.js` without a bundler
  - Runtime diagnostics and safety checks for props, version, and cross-reference
- **chirp-ui integration** — `chirp.ext.chirp_ui.use_chirp_ui(app)` registers chirp-ui static files (CSS, themes).
  Template loader auto-detects chirp-ui when installed. Optional `ui` extra: `pip install bengal-chirp[ui]`
- **Auth hardening** — Production-ready authentication and abuse protection:
  - `AuthRateLimitMiddleware` — Rate limit login/reset endpoints
  - `LoginLockout` — Lockout and backoff for repeated failures
  - `SecurityAudit` — Audit events for failures, lockouts, and blocked attempts
- **Alpine.js support** — `chirp/alpine.html` macros for `x-data`, `x-init`, reactive bindings.
  Server-side Alpine integration and `app.check()` validation for Alpine islands
- **LLM playground example** — New example app demonstrating streaming LLM chat with htmx
- **Documentation** — Guides for islands, auth hardening, Alpine + htmx, and no-build high-state

### Changed

- **Dependencies** — `kida-templates>=0.2.2` (was 0.2.1)
- **CI** — Ruff linting, prek pre-commit, GitHub Actions workflow
- **RAG demo** — Updated with chirp-ui integration

### Fixed

- Various test and type fixes across examples and core modules

[0.1.2]: https://github.com/lbliii/chirp/releases/tag/v0.1.2

## [0.1.1] — 2026-02-15

### Added

- **`chirp` CLI** — New console entry point with three subcommands:
  - `chirp new <name> [--minimal]` — Scaffold a project with app, templates, static assets,
    and tests. `--minimal` generates a single-file starter.
  - `chirp run <app> [--host HOST] [--port PORT]` — Start the dev server from an import
    string (e.g. `chirp run myapp:app`).
  - `chirp check <app>` — Validate hypermedia contracts from the command line.
- **`Template.inline()`** — Prototyping shortcut that renders a template from a string
  instead of a file. Returns an `InlineTemplate` instance that works through content
  negotiation without requiring a `template_dir`.
- **`InlineTemplate`** — New return type for string-based template rendering. Separate
  from `Template` so negotiation can distinguish it and `app.check()` can warn about
  inline templates in production routes.
- **Built-in template filters** — `field_errors` extracts validation messages for a single
  form field from an errors dict. `qs` builds URL query strings, automatically omitting
  falsy values. Both are auto-registered in the Kida environment at startup.
- **`form_or_errors()`** — Glue function that combines `form_from()` and `ValidationError`
  into a single call. Returns `T | ValidationError`, eliminating the try/except boilerplate
  for form binding errors.
- **`form_values()`** — Utility that converts a dataclass or mapping to `dict[str, str]` for
  template re-population when validation fails.
- **Form field macros** — Shipped in `chirp/forms.html`, importable via
  `{% from "chirp/forms.html" import text_field %}`. Five macros (`text_field`,
  `textarea_field`, `select_field`, `checkbox_field`, `hidden_field`) render labelled
  fields with inline error display using the `field_errors` filter.
- **Filesystem-based page routing** — Layout-nested page discovery from directory structure.
- **`app.provide()`** — Dependency injection for request-scoped context providers.
- **Reactive block pipeline** — Structured reactive templates with derived state.
- **SSE safety checks** — Contract validation for event streams and event cross-reference.
- **Safe target** — `hx-target` safety for event-driven htmx elements.
- **Security headers middleware** — HSTS, X-Content-Type-Options, etc.
- **View transitions** — OOB swap support for View Transitions API.
- **Production deployment** — Pounce Phase 5 & 6 support, deployment documentation.
- **Typed extraction** — Query/form/JSON extraction via dataclasses in handler signatures.

### Dependencies

- `kida-templates>=0.2.1` — Template engine
- `bengal-pounce>=0.2.0` — ASGI server

[0.1.1]: https://github.com/lbliii/chirp/releases/tag/v0.1.1

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

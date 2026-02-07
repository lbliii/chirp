# Product Requirements Document: Chirp

**Version**: 0.1.0-draft
**Date**: 2026-02-07
**Status**: Draft

---

## 1. Overview

Chirp is a Python web framework for the modern web platform. It serves HTML -- full pages,
fragments, streams, and real-time events -- through its built-in template engine, kida.

Chirp targets Python 3.14+ with free-threading support and is designed for developers who
build content-driven web applications, internal tools, and interactive sites without reaching
for a JavaScript frontend framework.

---

## 2. Problem Statement

### 2.1 The Gap

Python web frameworks were designed for a web that no longer exists:

| Framework | Era | Assumption |
|-----------|-----|------------|
| Django | 2005 | Server renders full pages, forms POST and reload |
| Flask | 2010 | Minimal core, extensions for everything, WSGI |
| FastAPI | 2018 | Server is a JSON API, React/Vue handles the UI |

In 2026, the browser natively supports interactive UI patterns (`<dialog>`, `popover`, View
Transitions, container queries) that previously required JavaScript frameworks. The htmx
library proved that servers can send HTML fragments for partial page updates. Streaming HTML
delivers content progressively. Server-Sent Events push real-time updates over plain HTTP.

No Python framework is built around these capabilities.

### 2.2 Specific Gaps

1. **No fragment rendering.** No framework can render a named block from a template
   independently. Partial updates require separate template files or manual string slicing.

2. **No streaming HTML.** Templates render completely before sending. The browser waits for
   the entire page, even when the header and navigation are ready immediately.

3. **No first-class SSE.** Server-Sent Events require manual implementation or third-party
   extensions. Pushing rendered HTML fragments in real-time is not a supported pattern.

4. **No htmx awareness.** Frameworks don't distinguish between full page requests and
   fragment requests. Developers manually check headers and branch logic.

5. **No typed configuration.** Flask uses a mutable dict. FastAPI relies on Pydantic
   settings. Neither provides frozen, IDE-autocompletable config out of the box.

6. **No free-threading design.** Existing frameworks may pass tests on 3.14t but have
   global mutable state, unprotected caches, and mutable request/response objects.

---

## 3. Target Users

### 3.1 Primary: Full-Stack Python Developers

Developers who build web applications where the server renders HTML and the browser handles
presentation. They use htmx or vanilla JS for interactivity, not React/Vue/Angular. They
want type safety, modern Python, and minimal dependencies.

**Needs:**
- Fast time-to-hello-world (under 5 minutes)
- Template rendering with fragment support
- Real-time updates without WebSocket complexity
- Type-safe configuration and request handling
- Async-native for I/O-bound operations (database, external APIs, LLMs)

### 3.2 Secondary: Tool and Dashboard Builders

Developers building internal tools, admin dashboards, monitoring UIs, and developer
utilities. These applications are content-heavy, read-heavy, and benefit from server-rendered
HTML with real-time sprinkles.

**Needs:**
- SSE for live data feeds (logs, metrics, notifications)
- Streaming HTML for dashboards with multiple data sources
- Session management for authentication
- Simple deployment (single Python process)

### 3.3 Tertiary: Content Platform Developers

Developers building forums, blogs, wikis, and collaborative content platforms. These
applications have user-generated content (often markdown), real-time presence indicators,
and thread-based interactions.

**Needs:**
- Markdown rendering (via patitas integration)
- Real-time updates (new posts, typing indicators, presence)
- Fragment rendering for infinite scroll and live updates
- Session/auth middleware support

---

## 4. Functional Requirements

### 4.1 Core HTTP (P0 -- Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-001 | Route registration via decorators | `@app.route("/path")` registers a handler |
| F-002 | Path parameters with type conversion | `"/users/{id}"` extracts `id: int` |
| F-003 | HTTP method filtering | `methods=["GET", "POST"]` on routes |
| F-004 | Immutable Request object | Frozen metadata, async body access |
| F-005 | Chainable Response object | `.with_status()`, `.with_header()`, `.with_cookie()` |
| F-006 | Return-value content negotiation | str, dict, bytes, Response, Redirect |
| F-007 | Typed frozen configuration | `AppConfig` dataclass with IDE autocomplete |
| F-008 | ASGI interface | Implements ASGI 3.0 callable |
| F-009 | Development server | `app.run()` starts a dev server with auto-reload |
| F-010 | Error handlers | `@app.error(404)` and `@app.error(ExceptionType)` |

### 4.2 Template Rendering (P0 -- Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-011 | Template return type | `return Template("page.html", **ctx)` renders via kida |
| F-012 | Template filter registration | `@app.template_filter()` decorator |
| F-013 | Template global registration | `@app.template_global()` decorator |
| F-014 | Auto-reload in debug mode | Templates reload on file change |

### 4.3 Fragment Rendering (P0 -- Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-015 | Fragment return type | `return Fragment("page.html", "block_name", **ctx)` |
| F-016 | Fragment request detection | `request.is_fragment` detects HX-Request header |
| F-017 | Block-level rendering in kida | Render a named block without the full template |

### 4.4 Middleware (P1 -- Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-018 | Protocol-based middleware | Functions and callables matching the protocol |
| F-019 | Middleware pipeline | Ordered execution with next-handler chaining |
| F-020 | CORS middleware (built-in) | Configurable origins, methods, headers |
| F-021 | Static file serving | Serve files from a directory |
| F-022 | Session middleware | Signed cookies via optional itsdangerous dep |

### 4.5 Streaming HTML (P1 -- Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-023 | Stream return type | `return Stream("page.html", **async_ctx)` |
| F-024 | Chunked transfer encoding | Response streams as template sections complete |
| F-025 | Async context resolution | Awaitable values resolve and stream independently |

### 4.6 Server-Sent Events (P1 -- Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-026 | EventStream return type | `return EventStream(async_generator)` |
| F-027 | SSE protocol | Proper `text/event-stream` with `data:`, `event:`, `id:` |
| F-028 | Fragment SSE events | Yield Fragment objects in SSE streams |
| F-029 | Connection lifecycle | Heartbeat, disconnect detection, cleanup |

### 4.7 Testing (P1 -- Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-030 | Test client | `async with TestClient(app) as client:` |
| F-031 | Same types in test and production | Response in tests is the same Response type |
| F-032 | Fragment test helpers | Assert on fragment content, absence of wrapper |
| F-033 | SSE test helpers | Consume and assert on SSE event streams |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NF-001 | Startup time | < 500ms for a 50-route app |
| NF-002 | Memory baseline | < 30MB RSS for idle app |
| NF-003 | Request throughput | > 10,000 req/s for simple HTML response |
| NF-004 | Route matching | O(1) average case via compiled route table |
| NF-005 | Template rendering | Within 10% of kida standalone performance |

### 5.2 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NF-006 | Free-threading safety | No data races under concurrent load on 3.14t |
| NF-007 | Graceful error handling | Unhandled exceptions produce 500, never crash server |
| NF-008 | SSE resilience | Disconnected clients cleaned up, no resource leaks |

### 5.3 Developer Experience

| ID | Requirement | Target |
|----|-------------|--------|
| NF-009 | Hello world | < 5 lines, < 2 minutes to running server |
| NF-010 | Type checker clean | Zero `type: ignore` in framework code |
| NF-011 | IDE autocomplete | All public APIs fully typed for autocomplete |
| NF-012 | Error messages | Actionable errors with fix suggestions |
| NF-013 | Import surface | Single import for common use: `from chirp import App` |

### 5.4 Compatibility

| ID | Requirement | Target |
|----|-------------|--------|
| NF-014 | Python version | >= 3.14 |
| NF-015 | Free-threading | Full support for 3.14t (no-GIL) |
| NF-016 | ASGI servers | Compatible with uvicorn, hypercorn, granian |
| NF-017 | Platforms | Linux, macOS, Windows |

---

## 6. Dependency Budget

### Core (always installed)

| Dependency | Purpose | Size | Justification |
|------------|---------|------|---------------|
| kida | Template engine | ~50KB | Same ecosystem, built-in feature |
| anyio | Async runtime | ~100KB | Mature, minimal, backend-agnostic |

### Optional Extras

| Extra | Dependency | Purpose |
|-------|------------|---------|
| `chirp[forms]` | python-multipart | Multipart form parsing |
| `chirp[sessions]` | itsdangerous | Signed cookie sessions |
| `chirp[testing]` | httpx | Test client transport |

### Excluded

| Dependency | Reason |
|------------|--------|
| starlette | Chirp owns its HTTP layer |
| pydantic | Not needed; frozen dataclasses suffice |
| click | CLI is optional; `app.run()` is the entry point |
| werkzeug | WSGI; chirp is ASGI-only |
| jinja2 | Replaced by kida |

---

## 7. Success Criteria

### 7.1 v0.1.0 (Phase 0-1)

- Hello world runs in 5 lines
- Routes, path params, content negotiation work
- Request is frozen, Response is chainable
- ASGI handler passes basic compliance
- Dev server starts with `app.run()`

### 7.2 v0.2.0 (Phase 2-3)

- Template and Fragment return types work
- `request.is_fragment` detects htmx requests
- Block-level rendering produces correct HTML
- A simple htmx search example works end-to-end

### 7.3 v0.3.0 (Phase 4-5)

- Middleware pipeline works
- Sessions and CORS are usable
- Streaming HTML sends chunks progressively
- Dashboard example streams multiple data sources

### 7.4 v0.4.0 (Phase 6-7)

- SSE works with fragment rendering
- Test client covers all return types
- Real-time notification example works
- Documentation site exists

---

## 8. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ~~Kida lacks block-level rendering~~ | ~~Blocks Phase 3~~ | ~~Medium~~ | **RESOLVED**: `render_block()` integrated in Phase 2; 12 contract tests in kida repo |
| Kida lacks streaming rendering | Blocks Phase 5 | Medium | `RenderedTemplate` stub exists; plan compiler work alongside Phases 3-4 |
| Streaming HTML mid-stream errors | Poor UX on failure | Medium | Define error recovery protocol; test extensively |
| anyio compatibility issues on 3.14t | Blocks free-threading | Low | anyio already tests on 3.14; monitor upstream |
| htmx changes fragment detection pattern | Breaks `is_fragment` | Low | Abstract detection behind a method; easy to update |
| Scope creep toward "full framework" | Dilutes focus | High | Non-goals list is enforced; review each addition |

---

## 9. Out of Scope

See ROADMAP.md Non-Goals section. Additionally:

- GraphQL support
- WebSocket support (SSE covers the use cases; WebSocket may come later)
- Built-in database migrations
- Background job scheduling
- Email sending
- CLI scaffolding / project generators
- Plugin/extension registry

---

## 10. Open Questions

1. **Should chirp include a minimal CLI?** `chirp run` vs just `app.run()` and `python app.py`.
   Leaning toward no CLI initially -- `app.run()` is sufficient and avoids a click dependency.

2. **Should `Stream` require kida changes or work with the existing API?** The streaming
   renderer may need kida to yield chunks from a template render. This needs a kida spike
   before Phase 5.

3. **What ASGI server to recommend for production?** uvicorn is the default choice, but
   granian (Rust-based) may be a better fit for free-threading. Needs benchmarking.

4. **Should fragment detection support more than htmx?** Turbo, Unpoly, and custom headers
   all indicate fragment requests. Consider an extensible detection mechanism.

5. **JSON API support level.** Returning dicts produces JSON. Should chirp also support
   typed response models (dataclass -> JSON serialization) or stay minimal?

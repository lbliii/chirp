---
title: API Reference
description: Public API exports and type signatures
draft: false
weight: 10
lang: en
type: doc
tags: [reference, api, exports]
keywords: [api, reference, exports, chirp, public-api, types]
category: reference
---

## Public API

Everything you need is importable from `chirp`:

```python
from chirp import (
    # Core
    App,
    AppConfig,

    # HTTP
    Request,
    Response,
    Redirect,

    # Template return types
    Template,
    Fragment,
    Page,
    Stream,
    ValidationError,
    OOB,

    # Real-time
    EventStream,
    SSEEvent,

    # Middleware types
    Middleware,
    Next,
    AnyResponse,

    # Context
    g,
    get_request,

    # Auth
    get_user,
    login,
    logout,
    login_required,
    requires,
    is_safe_url,

    # Errors
    ChirpError,
    ConfigurationError,
    HTTPError,
    MethodNotAllowed,
    NotFound,

    # Tools
    ToolCallEvent,
)
```

## Core

### App

The application class. Mutable during setup, frozen at runtime.

```python
app = App(config=AppConfig(...))
```

**Decorators:**

| Decorator | Description |
|-----------|-------------|
| `@app.route(path, methods=...)` | Register a route handler |
| `@app.error(code_or_type)` | Register an error handler |
| `@app.template_filter(name=...)` | Register a kida template filter |
| `@app.template_global(name=...)` | Register a kida template global |
| `@app.on_startup` | Register a startup callback |
| `@app.on_shutdown` | Register a shutdown callback |
| `@app.on_worker_startup` | Register a per-worker startup callback |
| `@app.on_worker_shutdown` | Register a per-worker shutdown callback |
| `@app.tool(name, description)` | Register an MCP tool |

**Methods:**

| Method | Description |
|--------|-------------|
| `app.add_middleware(mw)` | Add middleware to the pipeline |
| `app.run()` | Start the development server (freezes the app) |
| `app.check()` | Validate hypermedia contracts |

### AppConfig

Frozen dataclass for application configuration. See [[docs/core-concepts/configuration|Configuration]].

## HTTP

### Request

Frozen dataclass representing an incoming HTTP request.

**Properties:** `method`, `path`, `query`, `headers`, `cookies`, `content_type`

**htmx Properties:** `is_fragment`, `htmx_target`, `htmx_trigger`, `is_history_restore`

**Async Methods:** `body()`, `text()`, `json()`, `form()`, `stream()`

### Response

HTTP response with chainable `.with_*()` API.

**Methods:** `with_status()`, `with_header()`, `with_headers()`, `with_content_type()`, `with_cookie()`, `without_cookie()`, `with_hx_redirect()`, `with_hx_location()`, `with_hx_trigger()`, `with_hx_trigger_after_settle()`

### Redirect

Convenience for 302 redirects: `Redirect(url)`.

## Template Return Types

| Type | Description |
|------|-------------|
| `Template(name, **ctx)` | Full template render |
| `Fragment(name, block, **ctx)` | Named block render |
| `Page(name, block, **ctx)` | Auto-detect fragment vs full page |
| `Stream(name, **ctx)` | Progressive streaming render |
| `ValidationError(name, block, **ctx)` | 422 fragment response |
| `OOB(main, *fragments)` | Out-of-band multi-fragment response |

## Real-Time

| Type | Description |
|------|-------------|
| `EventStream(generator)` | Server-Sent Event stream |
| `SSEEvent(data, event, id, retry)` | Structured SSE event |

## Context

| Export | Description |
|--------|-------------|
| `g` | Request-scoped mutable namespace (ContextVar-backed) |
| `get_request()` | Get the current request from ContextVar |

## Auth

| Export | Description |
|--------|-------------|
| `get_user()` | Get the current authenticated user (or `AnonymousUser`) |
| `login(user)` | Regenerate session and set the authenticated user |
| `logout()` | Regenerate session and clear the authenticated user |
| `@login_required` | Decorator: require authentication |
| `@requires(*permissions)` | Decorator: require specific permissions |
| `is_safe_url(url)` | Check whether a redirect URL is safe (relative, same origin) |

See [[docs/middleware/builtin|Built-in Middleware]] for setup and usage.

## Errors

| Error | Description |
|-------|-------------|
| `ChirpError` | Base exception for all Chirp errors |
| `ConfigurationError` | Invalid configuration (missing secret_key, etc.) |
| `HTTPError` | Base for HTTP errors |
| `NotFound` | 404 Not Found |
| `MethodNotAllowed` | 405 Method Not Allowed |

## Next Steps

- [[docs/reference/errors|Errors]] -- Error handling in detail
- [[docs/core-concepts/return-values|Return Values]] -- Return type guide
- [[docs/core-concepts/configuration|Configuration]] -- AppConfig options

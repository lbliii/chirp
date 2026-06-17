---
title: Custom Middleware
description: Writing your own middleware with functions and classes
draft: false
weight: 30
lang: en
type: doc
tags: [middleware, custom, patterns]
keywords: [custom-middleware, function, class, pattern, rate-limit, timing]
category: guide
---

## Overview

Middleware wraps every request and response. It runs before your handler sees
the request and after your handler returns, so it's where cross-cutting work
lives: logging, auth, rate limiting, timing, security headers.

A middleware is any async callable matching `async def mw(request, next) ->
Response`. Call `await next(request)` to pass control down [[docs/build-apps/request-pipeline/_index|the request pipeline]],
then inspect or replace what comes back.

Reach for custom middleware when the work applies to many routes. For one route,
do it in the handler. Chirp already ships the common middleware — sessions, CSRF,
security headers — so check [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]]
before writing your own.

:::{note}
Middleware satisfies a `Middleware` Protocol — both plain functions and callable
classes work. The framework checks the shape, not the lineage.
:::

## Define a middleware

The shortest middleware is a function. Use a class when you need configuration
or state.

::::{tab-set}
::::{tab-item} Function
Wrap the request, measure it, add a header on the way out:

```python
import time
from chirp import Request, Response, Next

async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    return response.with_header("X-Response-Time", f"{elapsed:.3f}s")

app.add_middleware(timing)
```
::::{/tab-item}
::::{tab-item} Class
Give the class an `async __call__`. Configuration and state live on the instance:

```python
import threading
import time
from chirp import Request, Response, Next

class RateLimiter:
    def __init__(self, max_requests: int, window: float) -> None:
        self.max_requests = max_requests
        self.window = window
        self._counts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    async def __call__(self, request: Request, next: Next) -> Response:
        client_ip = request.headers.get("X-Forwarded-For", "unknown")

        with self._lock:
            now = time.monotonic()
            hits = self._counts.setdefault(client_ip, [])
            # Remove expired entries
            hits[:] = [t for t in hits if now - t < self.window]

            if len(hits) >= self.max_requests:
                return Response("Too Many Requests").with_status(429)
            hits.append(now)

        return await next(request)

app.add_middleware(RateLimiter(max_requests=100, window=60.0))
```
::::{/tab-item}
::::{/tab-set}

:::{danger} Shared instance state must be locked
A class middleware is a single instance shared across every concurrent request
under [[docs/about/thread-safety|free-threading]]. Mutable instance state —
counters, caches, the rate-limiter dict above — **must** be guarded by a
`threading.Lock`, or concurrent requests will corrupt it silently. For
per-request state, use `g` (below), never instance attributes.
:::

## Common patterns

### Request logging

```python
async def request_logger(request: Request, next: Next) -> Response:
    print(f"→ {request.method} {request.path}")
    response = await next(request)
    print(f"← {response.status} {request.path}")
    return response
```

### Error handling

```python
async def error_boundary(request: Request, next: Next) -> Response:
    try:
        return await next(request)
    except Exception as e:
        print(f"Error: {e}")
        return Response("Internal Server Error").with_status(500)
```

### Request context

Use `g`, the [[docs/about/thread-safety|request-scoped]] namespace, to pass data
between middleware and handlers:

```python
from chirp import g

async def load_user(request: Request, next: Next) -> Response:
    token = request.cookies.get("session_token")
    if token:
        g.user = await get_user_from_token(token)
    else:
        g.user = None
    return await next(request)
```

Then in handlers:

```python
from chirp import Redirect, Template, g

@app.route("/profile")
def profile():
    if not g.user:
        return Redirect("/login")
    return Template("profile.html", user=g.user)
```

`g` is backed by a `ContextVar`, so each request gets its own namespace.

:::{note} See also
- [[docs/about/thread-safety|Thread Safety]] — the free-threading model behind `g`
:::

### Conditional middleware

Skip middleware for certain paths:

```python
async def auth_required(request: Request, next: Next) -> Response:
    public_paths = {"/", "/login", "/health"}
    if request.path in public_paths:
        return await next(request)

    if not request.cookies.get("session"):
        return Redirect("/login")

    return await next(request)
```

### Response transformation

For standard security headers, add the built-in
[[docs/build-apps/request-pipeline/builtin|`SecurityHeadersMiddleware`]] rather
than rolling your own:

```python
from chirp.middleware import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware())
```

:::{dropdown} Advanced: setting headers by hand
When you need headers the built-in doesn't cover, transform the response after
the handler returns:

```python
async def add_security_headers(request: Request, next: Next) -> Response:
    response = await next(request)
    return (
        response
        .with_header("X-Content-Type-Options", "nosniff")
        .with_header("X-Frame-Options", "DENY")
        .with_header("Referrer-Policy", "strict-origin-when-cross-origin")
    )
```
:::{/dropdown}

## Next steps

- [[docs/build-apps/request-pipeline/_index|Request Pipeline]] — how the chain composes and orders
- [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]] — what ships with Chirp
- [[docs/about/thread-safety|Thread Safety]] — free-threading patterns for shared state

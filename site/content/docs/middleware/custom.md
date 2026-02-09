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

## Function Middleware

The simplest middleware is a function:

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

## Class Middleware

For middleware that needs configuration or state, use a class with `__call__`:

```python
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

Both function and class middleware satisfy the `Middleware` protocol. The framework checks the shape, not the lineage.

## Common Patterns

### Request Logging

```python
async def request_logger(request: Request, next: Next) -> Response:
    print(f"→ {request.method} {request.path}")
    response = await next(request)
    print(f"← {response.status} {request.path}")
    return response
```

### Error Handling

```python
async def error_boundary(request: Request, next: Next) -> Response:
    try:
        return await next(request)
    except Exception as e:
        print(f"Error: {e}")
        return Response("Internal Server Error").with_status(500)
```

### Request Context

Use `g` (the request-scoped namespace) to pass data between middleware and handlers:

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
@app.route("/profile")
def profile():
    if not g.user:
        return Redirect("/login")
    return Template("profile.html", user=g.user)
```

`g` is backed by a `ContextVar`, so each request gets its own namespace. Safe under free-threading.

### Conditional Middleware

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

### Response Transformation

Modify responses after the handler:

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

## Thread Safety

Under free-threading, multiple middleware instances run concurrently. If your class middleware has mutable state, protect it with a lock:

```python
class Counter:
    def __init__(self) -> None:
        self._count = 0
        self._lock = threading.Lock()

    async def __call__(self, request: Request, next: Next) -> Response:
        with self._lock:
            self._count += 1
            count = self._count
        response = await next(request)
        return response.with_header("X-Request-Count", str(count))
```

For per-request state, use `g` or `ContextVar` instead of instance variables.

## Next Steps

- [[docs/middleware/overview|Overview]] -- Middleware pipeline mechanics
- [[docs/middleware/builtin|Built-in Middleware]] -- What ships with Chirp
- [[docs/about/thread-safety|Thread Safety]] -- Free-threading patterns

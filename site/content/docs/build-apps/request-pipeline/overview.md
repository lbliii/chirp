---
title: Overview
description: How Chirp's protocol-based middleware works — the function shape, the pipeline order, and how to short-circuit
draft: false
weight: 10
lang: en
type: doc
tags: [middleware, protocol, pipeline]
keywords: [middleware, protocol, pipeline, next, request, response, short-circuit]
category: guide
---

## Overview

Middleware is code that runs *around* your route handlers — before the request
reaches them and after they return a response. Reach for it when behavior
belongs to every route (logging, auth gates, response headers) rather than to
one handler.

In Chirp a middleware is an async function. There's no base class to subclass and
no decorator to apply — you write a function matching one shape and register it:

```python
from chirp import Next, Request, AnyResponse

async def my_middleware(request: Request, next: Next) -> AnyResponse:
    # before the handler runs
    response = await next(request)
    # after the handler returns
    return response
```

That is the entire contract: a callable that takes a `Request` and a `Next`, and
returns a response. `next` invokes the rest of the pipeline — the next middleware,
or the handler itself. Whatever a handler returns flows back through as a
response, because in Chirp [[docs/about/core-concepts/return-values|the return type is the intent]].

## The pipeline

Each middleware wraps the next, so a request passes through them on the way in and
back out on the way out:

```
Request → Middleware A → Middleware B → Route Handler → Response
                                   ↩ Middleware B ↩ Middleware A → Client
```

You register middleware in setup order:

```python
app.add_middleware(timing_middleware)
app.add_middleware(cors_middleware)
app.add_middleware(auth_middleware)
```

:::{note}
The first middleware you register runs **first** on the way in and **last** on
the way out. Here `timing_middleware` is the outermost layer — it sees the total
time including CORS and auth processing.
:::

### Explicit ordering with `priority`

When registration order is awkward (for example a plugin adds middleware you want
to keep outermost regardless of where its setup runs), pass a keyword-only
`priority` so the order is explicit and independent of registration order:

```python
app.add_middleware(timing_middleware, priority=-100)  # always outermost
app.add_middleware(cors_middleware)                    # priority 0 (default)
app.add_middleware(auth_middleware, priority=10)       # innermost of the three
```

**Lower priority runs outermost.** At freeze the user middleware is sorted by
`(priority, registration_order)` with a *stable* sort, so equal-priority
middleware keep their registration order and a stack that never passes `priority`
is byte-identical to plain registration order. Built-in middleware (allowed-hosts,
CSP nonce, security headers, injection) stays positionally pinned around your
chain — `priority` only reorders middleware you register.

A `priority` that would place `CSRFMiddleware` outside `SessionMiddleware` still
raises `ConfigurationError` at freeze (CSRF reads the session). `app.check()`
reports the resolved order under the INFO `middleware_chain` diagnostic so you
can confirm the pipeline you registered is the pipeline that runs.

## What you can do in a middleware

Inside the function you control both halves of the round trip:

```python
from chirp import Next, Request, AnyResponse

async def logging_middleware(request: Request, next: Next) -> AnyResponse:
    # runs before the handler
    print(f"Incoming: {request.method} {request.path}")

    response = await next(request)

    # runs after the handler
    print(f"Response: {response.status}")
    return response
```

From here you can:

- Modify the request before passing it to `next`.
- Short-circuit by returning a response without calling `next`.
- Modify the response after `next` returns.
- Catch exceptions raised from `next`.

A class with an `async def __call__(self, request, next)` method matches the same
shape, so stateful middleware (rate limiters, counters) is a callable object
rather than a function.

### Short-circuiting

Return a response without calling `next` to block the request before it reaches
any handler:

```python
from chirp import Next, Request, AnyResponse, Response

async def auth_guard(request: Request, next: Next) -> AnyResponse:
    if not request.headers.get("Authorization"):
        return Response("Unauthorized").with_status(401)
    return await next(request)
```

`.with_status()` and `.with_header()` are chainable and return a new response, so
you can adjust status and headers inline.

:::{dropdown} Advanced: streaming, SSE, and file responses
A middleware's `Next` returns `AnyResponse` — the union of every response type the
pipeline can produce: `Response`, `StreamingResponse`, `SSEResponse`, and
`FileResponse`. All four share the chainable `.with_status()` / `.with_header()`
API, so a middleware can set status and headers uniformly across them.

For most middleware you only touch `Response`. Streaming, SSE, and file responses
pass through middleware, but their bodies are produced lazily and cannot be
inspected synchronously — you can wrap or annotate them, not read their content
in the middleware. If you need to reason about *what* a handler is rendering
rather than the raw response, you can
[[docs/build-apps/request-pipeline/render-plan|inspect the RenderPlan from middleware]]
instead.
:::

:::{note} See also
- [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]] — CORS, static files, sessions, CSRF, security headers, and more
- [[docs/build-apps/request-pipeline/custom|Custom Middleware]] — writing and testing your own
- [[docs/build-apps/pages-navigation/routes|Routes]] — what middleware wraps
- [[docs/about/core-concepts/return-values|Return values]] — why handlers return types, not response objects
:::

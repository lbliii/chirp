---
title: Overview
description: How Chirp's protocol-based middleware works
draft: false
weight: 10
lang: en
type: doc
tags: [middleware, protocol, pipeline]
keywords: [middleware, protocol, pipeline, next, request, response]
category: guide
---

## No Base Class

Chirp middleware uses a Protocol, not inheritance. A middleware is anything that matches this shape:

```python
async def my_middleware(request: Request, next: Next) -> Response:
    # Before the handler
    response = await next(request)
    # After the handler
    return response
```

That is the entire contract. A function that takes a `Request` and a `Next` callable, returns a `Response`.

## The Pipeline

Middleware forms a pipeline. Each middleware wraps the next:

```
Request → Middleware A → Middleware B → Route Handler → Response
                                   ↩ Middleware B ↩ Middleware A → Client
```

Middleware registered first runs first on the way in and last on the way out.

## Registration

```python
app.add_middleware(timing_middleware)
app.add_middleware(cors_middleware)
app.add_middleware(auth_middleware)
```

Order matters. In this example, `timing_middleware` wraps everything -- it sees the total time including CORS and auth processing.

## The Next Callable

`Next` is a callable that invokes the rest of the pipeline:

```python
from chirp import Next

async def my_middleware(request: Request, next: Next) -> Response:
    # Runs before the handler
    print(f"Incoming: {request.method} {request.path}")

    # Call the next middleware (or the handler)
    response = await next(request)

    # Runs after the handler
    print(f"Response: {response.status}")
    return response
```

You can:
- Modify the request before passing it to `next`
- Short-circuit by returning a response without calling `next`
- Modify the response after `next` returns
- Catch exceptions from `next`

## Short-Circuiting

Return early without calling `next` to block the request:

```python
async def auth_guard(request: Request, next: Next) -> Response:
    if not request.headers.get("Authorization"):
        return Response("Unauthorized").with_status(401)
    return await next(request)
```

## Response Types

Middleware handles all response types through the `AnyResponse` union:

```python
from chirp import AnyResponse  # Response | StreamingResponse | SSEResponse
```

For most middleware, you only need to work with `Response`. Streaming and SSE responses pass through middleware but their bodies cannot be inspected synchronously.

## Next Steps

- [[docs/middleware/builtin|Built-in Middleware]] -- CORS, StaticFiles, Sessions, and more
- [[docs/middleware/custom|Custom Middleware]] -- Writing your own middleware
- [[docs/routing/routes|Routes]] -- What middleware wraps

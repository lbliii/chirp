---
title: Philosophy
description: The design principles that shape every Chirp decision
draft: false
weight: 10
lang: en
type: doc
tags: [philosophy, design, principles]
keywords: [philosophy, design, principles, ergonomic, honest, transparent]
category: explanation
---

Chirp's API didn't fall out of one big decision -- it falls out of a handful of consistent instincts about what a web framework should and shouldn't do for you. This page names those instincts so you can judge whether Chirp's bets match yours. If you'd rather see the code, jump to [[docs/about/architecture|Architecture]]; if you want the hard lines on what Chirp won't do, see [[docs/about/non-goals|Non-Goals]].

## Design Principles

These are distilled from building bengal, kida, patitas, and rosettes -- not as rigid rules, but as consistent instincts that shape every decision.

:::{steps}
:::{step} The obvious thing should be the easy thing

```python
app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

You never make someone understand the system to use the system. The simple call works. The architecture reveals itself only when you need it.

Five lines to hello world. Return a string, get a response. Return a `Template`, get rendered HTML. Return a `Fragment`, get a block. [[docs/about/core-concepts/return-values|The type *is* the intent]].

:::{/step}
:::{step} Data should be honest about what it is

If something doesn't change after creation, it shouldn't pretend it might. If something is built incrementally, it should be honest about that too.

- `Request` is frozen. Received data doesn't change.
- `Response` is built through `.with_*()` chains. It is constructed incrementally, then sent.
- `AppConfig` is frozen. Configuration doesn't change at runtime.
- `Route` is frozen. The route table doesn't mutate after compile.

Don't force immutability where the shape of the problem is mutable -- match the tool to the truth. `g` is mutable because per-request state *is* mutable.

:::{/step}
:::{step} Extension should be structural, not ceremonial

Never make someone inherit from a base class just to participate. If a thing quacks like a middleware, it *is* a middleware.

```python
# A function is middleware
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    return response.with_header("X-Time", f"{time.monotonic() - start:.3f}")

# A class is middleware
class RateLimiter:
    async def __call__(self, request: Request, next: Next) -> Response:
        ...
```

The system discovers capability from shape, not from lineage. The `Middleware` protocol accepts either.

:::{/step}
:::{step} The system should be transparent

No proxies hiding `type: ignore`. No magic globals. No "it works but don't look at how."

If someone reads the code, the flow is traceable from entry to exit:

- Request enters through the ASGI handler
- Middleware pipeline executes in registration order
- Router matches the path via trie lookup
- Handler is called with injected arguments
- Return value is negotiated into a response
- Response is sent back through the middleware stack

No hidden context, no implicit behavior, no action-at-a-distance. The full path -- from trie match to [[docs/about/architecture|the negotiated response]] -- is laid out in Architecture.

:::{/step}
:::{step} Own what matters, delegate what doesn't

Own the interface, own the developer experience, own the hot path. Delegate the commodity infrastructure.

- **Own**: Template integration (kida, same author), routing, middleware protocol, return-value negotiation, fragment rendering
- **Delegate**: Async runtime (anyio), form parsing (python-multipart), session signing (itsdangerous), password hashing (argon2)

Write the template engine because templates are the thing. Use anyio for the async runtime because writing your own is insane.

:::{/step}
:::{/steps}

## Non-Goals

Chirp deliberately holds **zero per-client server view state**, and the bright
lines that protect that property are maintained in one canonical place. A few
headlines:

- **No stateful ORM.** "SQL in, frozen dataclasses out" — database access is your choice.
- **No WebSocket return type.** SSE over WebSockets, always.
- **No WSGI, no Python floor below 3.14.** [[docs/about/thread-safety|The free-threading identity bet]].

For the full list — including in-core admin/CRUD, email, background jobs,
general rate limiting, and telemetry — and the honest alternative for each, see
the canonical [[docs/about/non-goals|Non-Goals]] doc.

## Next Steps

- [[docs/about/non-goals|Non-Goals]] -- The bright lines and the alternative for each
- [[docs/about/architecture|Architecture]] -- How these principles manifest in code
- [[docs/about/comparison|When to Use Chirp]] — Chirp's approach and fit
- [[docs/about/thread-safety|Thread Safety]] -- Free-threading patterns

---
title: App Lifecycle
description: How Chirp's App transitions from mutable setup to frozen runtime
draft: false
weight: 10
lang: en
type: doc
tags: [app, lifecycle, freeze, startup]
keywords: [app, lifecycle, freeze, mutable, immutable, startup, shutdown]
category: explanation
---

## Two Phases

A Chirp `App` has two distinct phases:

1. **Setup** -- mutable. Register routes, middleware, filters, error handlers.
2. **Runtime** -- frozen. The app compiles its route table, creates the kida environment, and becomes effectively immutable.

```python
from chirp import App

app = App()

# --- Setup phase (mutable) ---
@app.route("/")
def index():
    return "Hello"

@app.route("/about")
def about():
    return "About"

app.add_middleware(my_middleware)

# --- Freeze happens here ---
app.run()  # Compiles routes, freezes config, starts serving
```

The transition happens when `app.run()` is called, or on the first ASGI `__call__()`. After freeze, attempting to register new routes raises an error.

## Why Freeze?

Free-threading (Python 3.14t) means multiple threads handle requests concurrently. If the route table, middleware stack, or template environment could be mutated during request handling, you would need locks everywhere.

Instead, Chirp freezes the app once. All shared state becomes immutable. No locks needed for the hot path.

```
Setup Phase          Freeze          Runtime Phase
─────────────────────┬──────────────────────────────
@app.route()         │               Request handling
app.add_middleware() │  Compile       (immutable data)
@app.template_filter │  routes,       (no locks on
app.on_startup()     │  create env    shared state)
─────────────────────┴──────────────────────────────
```

## Lifecycle Hooks

Register callbacks for startup and shutdown:

```python
@app.on_startup
async def connect_db():
    app.db = await Database.connect("sqlite:///app.db")

@app.on_shutdown
async def close_db():
    await app.db.close()
```

For per-worker initialization (useful with multi-threaded serving):

```python
@app.on_worker_startup
async def init_worker():
    # Runs once per worker thread
    pass

@app.on_worker_shutdown
async def cleanup_worker():
    # Runs once per worker thread on shutdown
    pass
```

## Thread-Safe Freeze

The freeze operation uses double-check locking to be safe under free-threading:

```python
# Simplified -- actual implementation in app.py
if not self._frozen:
    with self._freeze_lock:
        if not self._frozen:
            self._compile_routes()
            self._create_kida_env()
            self._frozen = True
```

The first request (or `app.run()`) triggers the freeze. Concurrent requests block briefly on the lock, then proceed with the frozen state. After that, no synchronization is needed.

## Next Steps

- [[docs/core-concepts/return-values|Return Values]] -- What route handlers can return
- [[docs/core-concepts/configuration|Configuration]] -- All AppConfig fields
- [[docs/routing/routes|Routes]] -- Route registration in detail

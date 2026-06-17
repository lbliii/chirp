---
title: App Lifecycle
description: How Chirp's App transitions from mutable setup to frozen runtime
draft: false
weight: 80
lang: en
type: doc
tags: [app, lifecycle, freeze, startup]
keywords: [app, lifecycle, freeze, mutable, immutable, startup, shutdown]
category: explanation
---

# App Lifecycle

A Chirp `App` lives in two phases. During **setup** you register everything —
routes, middleware, filters, lifecycle hooks. Then the app **freezes**: it
compiles its route table, builds the [[docs/build-apps/html-fragments/kida-integration|kida]]
template environment, and becomes immutable so concurrent requests need no locks
on the hot path. Freeze happens automatically the first time you call `app.run()`
(or on the first request). After it, registering a new route raises an error.

## Two Phases

:::{steps}
:::{step} Setup (mutable)

Register routes, middleware, filters, error handlers, and lifecycle hooks. The
app is mutable during this phase.

:::{/step}
:::{step} Runtime (frozen)

The app compiles its route table, creates the kida environment, and becomes
immutable. All shared state is read-only.

:::{/step}
:::{/steps}

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

Freeze triggers when you call `app.run()`, or on the first ASGI request if you
serve the app through an external server. After freeze, registering a new route
raises an error.

If your app uses filesystem pages, register sections with `app.register_section()`
before `app.mount_pages()`. At freeze, the framework validates the route directory
contract, and in debug mode it runs `app.check()`.

:::{note} See also

[[docs/quality/contracts-debugging/route-contract|Route directory contract]] covers
what gets validated at freeze (section bindings, shell-mode block alignment, tab
hrefs) and how to fix each issue.
:::

## Why Freeze?

[[docs/about/thread-safety|Free-threading]] (Python 3.14t) lets multiple threads
handle requests at once. If the route table, middleware stack, or template
environment could change mid-request, you would need locks everywhere.

Instead, Chirp freezes the app once. All shared state becomes immutable, so the
request hot path needs no locks.

```
Setup Phase          Freeze          Runtime Phase
─────────────────────┬──────────────────────────────
@app.route()         │               Request handling
app.add_middleware() │  Compile       (immutable data)
@app.template_filter │  routes,       (no locks on
app.on_startup()     │  create env    shared state)
─────────────────────┴──────────────────────────────
```

Freeze is guarded by double-check locking: the first request or `app.run()`
triggers it, concurrent requests block briefly on the lock, then proceed against
the frozen state.

:::{dropdown} Advanced: how freeze stays thread-safe
The freeze operation uses double-check locking so it is safe under free-threading.
This is internal mechanism — you never call it directly.

```python
# Simplified — actual implementation is App._ensure_frozen / App._freeze
if not self._frozen:
    with self._freeze_lock:
        if not self._frozen:
            self._compile_routes()
            self._create_kida_env()
            self._frozen = True
```

The first request (or `app.run()`) triggers the freeze. Concurrent requests block
briefly on the lock, then proceed with the frozen state. After that, no
synchronization is needed on the hot path. The deep "why no locks" model lives in
[[docs/about/thread-safety|Thread Safety]].
:::{/dropdown}

## Lifecycle Hooks

Register callbacks for startup and shutdown. Use them to open and close a
resource you own — an HTTP client, a cache, a background queue — stashed somewhere
your handlers can reach it:

```python
import httpx

client: httpx.AsyncClient | None = None

@app.on_startup
async def open_client():
    global client
    client = httpx.AsyncClient(base_url="https://api.example.com")

@app.on_shutdown
async def close_client():
    if client is not None:
        await client.aclose()
```

:::{tip}
You do **not** need a hook for the database. Pass a connection URL to the app —
`app = App(db="sqlite:///app.db")` — and Chirp connects it on startup and
disconnects it on shutdown for you. Access it read-only via `app.db`. See
[[docs/build-apps/forms-data/database|Database]] for the full setup, including
passing a configured `Database` instance.
:::

For per-worker initialization — resources that must live on a worker's event
loop, such as async HTTP clients, async database pools, or per-worker caches —
use worker hooks:

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

:::{warning}
In production, worker hooks require `worker_mode="async"`. If you register worker
hooks while the effective worker mode is sync, Chirp rejects launch. See
[[docs/about/core-concepts/configuration|Configuration]] for how `worker_mode`
resolves.
:::

:::{dropdown} Advanced: worker hooks under sync vs async workers
Worker hooks are a production worker contract, not a general app-startup
replacement. Use `@app.on_startup` for everything that should run once when the
app boots.

On free-threaded Python, the `worker_mode="auto"` default resolves to sync
workers. Sync workers do not emit `pounce.worker.startup` or
`pounce.worker.shutdown` scopes, so Chirp rejects production launch when worker
hooks are registered and the effective worker mode is sync:

```python
app = App(AppConfig(debug=False, worker_mode="async"))
```

If a worker startup hook can fail in a way that must abort boot, put the
must-succeed check in `@app.on_startup` (which runs before workers spin up) or
expose a health check, rather than relying on worker-startup failure to stop the
server.
:::{/dropdown}

## Debug Checks at Freeze

In debug mode, freeze runs the same hypermedia contract checks as `app.check()`
and exits on ERROR. Opt out with `AppConfig(skip_contract_checks=True)` or the
`CHIRP_SKIP_CONTRACT_CHECKS` environment variable.

:::{note} See also

[[docs/quality/contracts-debugging/categories|Contract check categories]] lists
every rule the checker runs and its severity.
:::

## Next Steps

- [[docs/about/core-concepts/return-values|Return Values]] — what route handlers can return
- [[docs/about/core-concepts/configuration|Configuration]] — all `AppConfig` fields
- [[docs/build-apps/pages-navigation/routes|Routes]] — route registration in detail
- [[docs/about/thread-safety|Thread Safety]] — why frozen state needs no locks

:::{related}
:::

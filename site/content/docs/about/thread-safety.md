---
title: Thread Safety
description: How Chirp avoids data races by design on Python's free-threaded build
draft: false
weight: 40
lang: en
type: doc
tags: [thread-safety, free-threading, concurrency]
keywords: [thread-safety, free-threading, nogil, contextvar, immutable, frozen]
category: explanation
---

Chirp targets Python 3.14's **free-threaded** build, where many threads run Python
code at the same time with no [[docs/about/architecture|GIL]] (the global lock that
older builds used to let only one thread interpret bytecode at a time). Free-threading
removes the safety net that most Python web code quietly relies on — so Chirp avoids
data races by design rather than by hoping a lock happens to be in the right place.

The strategy is three tiers:

- **Shared state is immutable.** Config, requests, and the route table are frozen
  dataclasses. Many threads read them at once with zero synchronization.
- **Per-request state is isolated.** Anything that changes during a request lives in a
  `ContextVar` (a variable whose value is private to the current task/thread), so two
  concurrent requests never see each other's data.
- **Genuinely-shared mutable state is locked.** The handful of caches, registries, and
  event buses that multiple requests *do* write to are each guarded by an explicit lock.

An evaluator skimming the first screen should already have the model: read-only data is
free, request data is isolated, and the rest is locked.

:::{note}
This describes Chirp's *own* abstractions, which are free-threading safe. Shared mutable
state **you** add — a module-level dict, a counter, an in-process cache — is your
responsibility. The [When you need mutable state](#when-you-need-mutable-state) section
shows the pattern Chirp uses for exactly that.
:::

## At a glance

:::{list-table}
:header-rows: 1

* - Concern
  - Pattern
* - Configuration
  - Frozen dataclass — no locks
* - Request data
  - Frozen dataclass — no locks
* - Route table
  - Compiled at freeze, immutable after
* - Per-request state
  - `ContextVar` (`g`, `get_request()`)
* - Response building
  - Immutable `.with_*()` chains
* - Shared mutable state
  - Explicit `threading.Lock()`
* - Module-level state
  - None — no global mutables
:::

## Immutable data structures

Data that does not change after creation is frozen. Multiple threads read these
structures concurrently without any synchronization.

:::{list-table}
:header-rows: 1

* - Abstraction
  - Pattern
  - Why it's safe to share
* - `AppConfig`
  - `@dataclass(frozen=True, slots=True)`
  - Config does not change at runtime
* - `Request`
  - `@dataclass(frozen=True, slots=True)`
  - Received data does not change
* - `Route`
  - `@dataclass(frozen=True, slots=True)`
  - Routes do not change after compile
* - `Headers` / `QueryParams`
  - Immutable mappings
  - Request inputs do not change
* - `Router`
  - Compiled trie
  - The route table is built once, at freeze
:::

Responses follow the same rule. Each `.with_*()` returns a **new** object; the original
is never mutated, so middleware can transform a response without stepping on another
thread's copy:

```python
response = Response("OK")
response = response.with_header("X-Custom", "value")
response = response.with_status(201)
```

## ContextVar for request scope

Per-request state uses `ContextVar`, which gives each concurrent request its own
isolated value automatically:

```python
from contextvars import ContextVar

# Each request reads and writes its own value — never another request's.
request_var: ContextVar[Request] = ContextVar("chirp_request")
```

When you access `g.user` or call `get_request()`, you get the value for the *current*
request, no matter how many other requests are in flight. This is the same isolation
pattern kida uses for render context and patitas uses for parse config — no shared
mutable globals.

For per-request scratch state, use `g`. Each request gets its own namespace:

```python
from chirp import g

g.user = current_user
g.start_time = time.monotonic()
```

:::{note} See also

[[docs/about/core-concepts/return-values|Return values & request state]] covers the
`ContextVar`-backed `g` and `get_request()` in depth.
[[docs/build-apps/request-pipeline/custom|Custom middleware]] shows the thread-safe
patterns for middleware that reads or sets request state.
:::

## The freeze: setup → runtime

An `App` transitions from mutable (setup) to immutable (runtime) exactly **once**, and
that transition is guarded so concurrent first-requests are safe:

```python
# Setup phase — single-threaded, mutable
app = App()
app.add_middleware(cors)

@app.route("/")
def index():
    return "Hello"

# Freeze — compiles routes, creates the kida env, makes shared state immutable
app.run()

# Runtime phase — multi-threaded, immutable. No synchronization needed.
```

After freeze, every structure in the [At a glance](#at-a-glance) table is read-only, so
the hot request path takes no locks at all.

::::{dropdown} Inside the freeze: double-check locking
Freeze is the one place Chirp flips shared state from mutable to immutable, so it has to
be safe against several threads triggering the first request at once. It uses the
classic double-check pattern — a cheap unlocked check, then a lock, then a re-check
inside the lock so only one thread actually runs the freeze:

```python
def _ensure_frozen(self) -> None:
    if self._runtime_state.frozen:          # fast path — already frozen, no lock
        return
    # ... mount_app guard omitted ...
    with self._freeze_lock:
        if self._runtime_state.frozen:      # re-check under the lock
            return
        self._freeze()                      # runs exactly once
```

This snippet is illustrative; see
[`src/chirp/app/__init__.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/app/__init__.py)
for the exact `_ensure_frozen` source. The mechanics of the transition are covered in
[[docs/about/core-concepts/app-lifecycle|App lifecycle]].
::::

## No module-level mutable state

Chirp has no module-level mutable state — no global caches, module-level dicts, or
singletons that requests write to. Unguarded module-level state is the genuine
free-threading footgun, because the GIL used to hide the race for you:

:::{danger} Unguarded module-level state races under free-threading
The check-then-set below is a textbook data race: two threads can both see the key
missing and both run `compute(key)`, and the dict mutation itself is no longer protected
by a GIL.

```python
# WRONG — racy under free-threading
_cache = {}

def get_cached(key):
    if key not in _cache:
        _cache[key] = compute(key)   # two threads can both land here
    return _cache[key]
```

If the value is per-request, use a `ContextVar` instead of a shared dict. If it really is
shared across requests, guard it with a lock — see the next section.
:::

## When you need mutable state

Some state genuinely *is* shared across requests: caches, rate limiters, event buses,
registries. Chirp guards each one with an explicit `threading.Lock()`. The shape is
always the same — take the lock, touch the shared state, release:

```python
class ReactiveBus:
    def __init__(self, *, maxsize: int = 256) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self._emitted_count = 0

    def emit_sync(self, event: ChangeEvent) -> None:
        with self._lock:                         # critical section guarded
            queues = set(self._subscribers.get(event.scope, set()))
            self._emitted_count += 1
        for queue in queues:                     # work happens outside the lock
            queue.put_nowait(event)
```

Every shared-mutable-state primitive in Chirp is lock-guarded this way. Representative
examples include the in-memory cache backend, the in-memory rate-limit and lockout
backends, the OOB registry, the signal registry, the shape registry, and the
security audit sink — each with dedicated concurrency stress tests.

For state bound to a specific worker thread or event loop, use
`@app.on_worker_startup` / `@app.on_worker_shutdown` and run production with
`worker_mode="async"`. Pounce 0.7 sync workers do not emit worker-lifecycle scopes, so
Chirp fails production startup when worker hooks are registered and the effective worker
mode resolves to sync.

:::{note} See also

[[docs/quality/deployment/production|Production deployment]] covers `worker_mode` and
worker-lifecycle hooks for live deployments.
:::

## Stress-tested under contention

Every lock-protected module has concurrency stress tests in
[`tests/test_concurrency/`](https://github.com/lbliii/chirp/tree/main/tests/test_concurrency).

:::{list-table}
:header-rows: 1

* - Module
  - Test
  - What it proves
* - ReactiveBus
  - 100 subscribers, 50 emitter threads
  - No deadlock, no lost subscriptions
* - ReactiveBus
  - Queue saturation at capacity
  - Silent drop count is accurate
* - MemoryCacheBackend
  - 100 threads doing get/set/delete
  - No `KeyError`, no corrupt values
* - Rate limiter
  - 200 burst login attempts
  - Rate counts accurate (no under/over-counting)
* - Lockout backend
  - Concurrent lockout checks
  - Threshold triggers at the correct count
* - OOB registry
  - Concurrent contract builds
  - Single build, cache hit on subsequent access
* - ContextVar
  - 50 concurrent async tasks
  - Each task sees only its own `g`, request, and session
* - Database pool
  - 50 concurrent queries + parallel-reader timing
  - Readers run in parallel (WAL pool); writes serialize behind one writer; no pool exhaustion
:::

::::{dropdown} How these tests stay honest under contention
The stress tests use synchronized starts (for example `threading.Barrier` where
applicable), bounded iteration counts, and explicit timeouts to reduce flakiness under
real contention. Some async stress tests also use short `asyncio.sleep(...)` calls so
subscriber registration or processing completes before assertions run.
::::

## PEP 703 declaration

Chirp declares `_Py_mod_gil = 0`, which tells Python 3.14t that the framework is
free-threading safe and does not need the GIL re-enabled on its account.

::::{dropdown} What the declaration does
Under [PEP 703](https://peps.python.org/pep-0703/), an extension or module signals
free-threading safety by setting `_Py_mod_gil = 0`. Without it, importing the module on a
free-threaded build would re-enable the GIL process-wide. Chirp sets it in
[`src/chirp/__init__.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/__init__.py)
because every tier above — frozen shared state, `ContextVar` isolation, explicit locks —
holds without a GIL.
::::

## Code references

:::{list-table}
:header-rows: 1

* - Pattern
  - File
* - PEP 703 declaration
  - [`src/chirp/__init__.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/__init__.py)
* - Request / ContextVar (`g`, `get_request`)
  - [`src/chirp/context.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/context.py)
* - App freeze, double-check locking
  - [`src/chirp/app/__init__.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/app/__init__.py)
* - ReactiveBus (lock + observability)
  - [`src/chirp/pages/reactive/bus.py`](https://github.com/lbliii/chirp/blob/main/src/chirp/pages/reactive/bus.py)
* - Concurrency stress tests
  - [`tests/test_concurrency/`](https://github.com/lbliii/chirp/tree/main/tests/test_concurrency)
:::

:::{related}
:::

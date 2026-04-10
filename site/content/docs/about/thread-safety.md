---
title: Thread Safety
description: How Chirp makes data races structurally impossible
draft: false
weight: 40
lang: en
type: doc
tags: [thread-safety, free-threading, concurrency]
keywords: [thread-safety, free-threading, nogil, contextvar, immutable, frozen]
category: explanation
---

## By Architecture, Not by Testing

Chirp doesn't "pass tests on 3.14t." It makes data races structurally impossible through design choices baked into every abstraction.

## Immutable Data Structures

Data that doesn't change after creation is frozen:

| Abstraction | Pattern | Why |
|-------------|---------|-----|
| `AppConfig` | `@dataclass(frozen=True, slots=True)` | Config doesn't change at runtime |
| `Request` | `@dataclass(frozen=True, slots=True)` | Received data doesn't change |
| `Route` | `@dataclass(frozen=True, slots=True)` | Routes don't change after compile |
| `Headers` | Immutable mapping | Request headers don't change |
| `QueryParams` | Immutable mapping | Query parameters don't change |
| `Router` | Compiled trie | Route table doesn't change after freeze |

No locks needed. Multiple threads can read these structures concurrently without synchronization.

## ContextVar for Request Scope

Per-request state uses `ContextVar`, which provides automatic isolation between concurrent requests:

```python
from contextvars import ContextVar

# Each request gets its own copy
request_var: ContextVar[Request] = ContextVar("chirp_request")
# g uses a ContextVar-backed namespace (see context.py)
```

When you access `g.user` or `get_request()`, you get the value for the *current* request, regardless of how many other requests are being handled concurrently.

This is the same pattern used by patitas for `ParseConfig` and by kida for rendering context.

## Response Chains

Responses are built through immutable transformations:

```python
response = Response("OK")
response = response.with_header("X-Custom", "value")
response = response.with_status(201)
```

Each `.with_*()` returns a new object. The original is never mutated. Multiple middleware can transform responses without interference.

## App Freeze

The `App` transitions from mutable (setup) to immutable (runtime) exactly once:

```python
# Setup phase -- single-threaded, mutable
app = App()
app.add_middleware(cors)

@app.route("/")
def index():
    return "Hello"

# Freeze -- double-check locking
app.run()  # Compiles routes, creates kida env, sets _frozen = True

# Runtime phase -- multi-threaded, immutable
# All shared state is frozen. No synchronization needed.
```

The freeze uses double-check locking to be safe if multiple threads trigger it simultaneously:

```python
if not self._runtime_state.frozen:
    with self._freeze_lock:
        if not self._runtime_state.frozen:
            self._freeze()  # calls _compiler.freeze()
```

## Module-Level State

Chirp has no module-level mutable state. No global caches, no module-level dicts, no singletons.

Compare with typical Python patterns:

```python
# ❌ Not thread-safe (common in other frameworks)
_cache = {}

def get_cached(key):
    if key not in _cache:
        _cache[key] = compute(key)  # Race condition
    return _cache[key]

# ✅ Chirp pattern: ContextVar or locked cache
from contextvars import ContextVar
_request_cache: ContextVar[dict] = ContextVar("cache")
```

## _Py_mod_gil

Chirp declares `_Py_mod_gil = 0` (PEP 703), telling Python 3.14t that the module is free-threading safe. The GIL is not needed for Chirp's code.

## When You Need Mutable State

For shared mutable state (caches, rate limiters, event buses), use explicit locks. Chirp's `ReactiveBus` is the primary example -- it protects subscriber lists and observability counters under a single `threading.Lock`:

```python
class ReactiveBus:
    def __init__(self, *, maxsize: int = 256) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self._emitted_count = 0
        self._dropped_count = 0

    def emit_sync(self, event: ChangeEvent) -> None:
        with self._lock:
            queues = set(self._subscribers.get(event.scope, set()))
            self._emitted_count += 1
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with self._lock:
                    self._dropped_count += 1
```

The same pattern protects `MemoryCacheBackend`, `_InMemoryRateLimitBackend`, `_InMemoryLockoutBackend`, `OOBRegistry`, and `SecurityAuditLogger` -- 8 Lock sites total, each with dedicated concurrency stress tests.

For per-request mutable state, use `g`:

```python
from chirp import g

# Safe: each request gets its own g namespace
g.user = current_user
g.start_time = time.monotonic()
```

## Stress-Tested Under Contention

Every Lock-protected module has concurrency stress tests in `tests/test_concurrency/`. These use synchronized starts (for example, `threading.Barrier` where applicable), bounded iteration counts, and explicit timeouts to reduce flakiness under contention. Some async stress tests also use short `asyncio.sleep(...)` calls to allow subscriber registration or processing before assertions.

| Module | Test | What it proves |
|--------|------|---------------|
| ReactiveBus | 100 subscribers, 50 emitter threads | No deadlock, no lost subscriptions |
| ReactiveBus | Queue saturation at capacity | Silent drop count is accurate |
| MemoryCacheBackend | 100 threads doing get/set/delete | No `KeyError`, no corrupt values |
| Rate limiter | 200 burst login attempts | Rate counts accurate (no under/over-counting) |
| Lockout backend | Concurrent lockout checks | Threshold triggers at correct count |
| OOB registry | Concurrent contract builds | Single build, cache hit on subsequent access |
| ContextVar | 50 concurrent async tasks | Each task sees only its own `g`, `request_var`, `_session_var` |
| Database pool | 50 concurrent queries | No pool exhaustion, transactions serialize correctly |

## Summary

| Concern | Pattern |
|---------|---------|
| Configuration | Frozen dataclass |
| Request data | Frozen dataclass |
| Route table | Compiled at freeze, immutable after |
| Per-request state | ContextVar (`g`, `get_request()`) |
| Response building | Immutable `.with_*()` chains |
| Shared mutable state | Explicit `threading.Lock()` |
| Module-level state | None (no global mutables) |

## Code References

| Pattern | File |
|---------|------|
| PEP 703 declaration | [src/chirp/__init__.py](https://github.com/lbliii/chirp/blob/main/src/chirp/__init__.py) |
| Request/ContextVar (`g`, `get_request`) | [src/chirp/context.py](https://github.com/lbliii/chirp/blob/main/src/chirp/context.py) |
| App freeze, double-check locking | [src/chirp/app/__init__.py](https://github.com/lbliii/chirp/blob/main/src/chirp/app/__init__.py) |
| ReactiveBus (Lock + observability) | [src/chirp/pages/reactive/bus.py](https://github.com/lbliii/chirp/blob/main/src/chirp/pages/reactive/bus.py) |
| Concurrency stress tests | [tests/test_concurrency/](https://github.com/lbliii/chirp/tree/main/tests/test_concurrency) |

## Next Steps

- [[docs/about/architecture|Architecture]] -- System design
- [[docs/core-concepts/app-lifecycle|App Lifecycle]] -- The freeze transition
- [[docs/middleware/custom|Custom Middleware]] -- Thread-safe middleware patterns

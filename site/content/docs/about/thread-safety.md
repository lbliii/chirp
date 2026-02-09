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
_request_var: ContextVar[Request] = ContextVar("request")
_g_var: ContextVar[Namespace] = ContextVar("g")
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
if not self._frozen:
    with self._freeze_lock:
        if not self._frozen:
            self._compile()
            self._frozen = True
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

For shared mutable state (caches, rate limiters, metrics), use explicit locks:

```python
import threading

class MetricsCollector:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, metric: str) -> None:
        with self._lock:
            self._counts[metric] = self._counts.get(metric, 0) + 1
```

For per-request mutable state, use `g`:

```python
from chirp import g

# Safe: each request gets its own g namespace
g.user = current_user
g.start_time = time.monotonic()
```

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

## Next Steps

- [[docs/about/architecture|Architecture]] -- System design
- [[docs/core-concepts/app-lifecycle|App Lifecycle]] -- The freeze transition
- [[docs/middleware/custom|Custom Middleware]] -- Thread-safe middleware patterns

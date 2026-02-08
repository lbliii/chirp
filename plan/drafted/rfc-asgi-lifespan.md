# RFC: ASGI Lifespan Protocol Support

**Status**: Draft
**Created**: 2026-02-08
**Confidence**: 92% :green_circle:
**Category**: Server / ASGI

---

## Executive Summary

Chirp silently ignores ASGI lifespan scopes, which caused a deadlock with pounce (fixed server-side) and leaves apps with no supported pattern for startup/shutdown resource management. The `@app.on_startup` / `@app.on_shutdown` API is already used in the rag_demo example but not implemented. This RFC proposes implementing the lifespan protocol with decorator-based hooks, moving `_freeze()` into the startup phase, and updating `TestClient` to run lifespan events.

---

## Problem Statement

### Current State

Chirp's `__call__` delegates everything to `handle_request()`, which silently returns for non-HTTP scopes:

```
src/chirp/server/handler.py:40 — if scope["type"] != "http": return
```

The `App` class has no lifespan-related slots, hooks, or protocol handling:

```
src/chirp/app.py:48-61 — __slots__ has no lifespan fields
src/chirp/app.py:171-186 — __call__ passes all scopes to handle_request
```

**Evidence**:
- `src/chirp/server/handler.py:40` — non-HTTP scopes silently dropped
- `src/chirp/app.py:171-186` — `__call__` has no lifespan branch
- `src/chirp/app.py:190-202` — `_ensure_frozen()` runs on first request, not at startup

### Pain Points

1. **Deadlock with pounce** — pounce sends `lifespan.startup` and waits for `startup.complete`. Chirp returns silently. Pounce blocks forever. Server never accepts HTTP requests. (Fixed on pounce side but still architecturally wrong on chirp side.)

2. **No startup/shutdown hooks** — The `@app.on_startup` and `@app.on_shutdown` decorators are already used in the rag_demo example (`examples/rag_demo/app.py:97-122`) but are not implemented. Running the example would fail with `AttributeError`.

3. **Resource lifecycle gap** — `Database` (`src/chirp/data/database.py:189-229`) has explicit `connect()`/`disconnect()` methods designed for lifespan integration. Without lifespan support, apps must either lazy-connect on first query (adds latency, hides errors) or seed at module import time (like the dashboard example at `examples/dashboard/app.py:87`).

4. **Freeze timing** — `_ensure_frozen()` runs on the first HTTP request (`src/chirp/app.py:173`), adding compilation latency to the first user's response. Under free-threading, multiple workers race to freeze. Moving this to the lifespan startup phase would eliminate both issues.

5. **TestClient gap** — `TestClient.__aenter__` only calls `_ensure_frozen()` and `__aexit__` is a no-op (`src/chirp/testing/client.py:35-40`). Startup/shutdown hooks would not fire during tests.

### Impact

Every chirp app served by pounce (or any ASGI server that expects lifespan participation) is affected. The deadlock was a P0 blocker — apps literally couldn't serve requests until the pounce-side fix landed.

---

## Goals and Non-Goals

### Goals

1. Implement the ASGI lifespan protocol so chirp correctly responds to `lifespan.startup` and `lifespan.shutdown` events
2. Provide `@app.on_startup` and `@app.on_shutdown` decorator hooks matching the API already used in rag_demo
3. Move `_freeze()` into the lifespan startup phase (before first request, not during)
4. Update `TestClient` to fire startup/shutdown hooks during `__aenter__`/`__aexit__`

### Non-Goals

1. **Context-manager lifespan API** (like Starlette's `@app.lifespan`) — can be added later as a separate enhancement; decorator hooks are sufficient for the current API surface
2. **Lifespan state injection** — passing startup-created objects into request scope (Starlette's `state` pattern); out of scope for this RFC
3. **Graceful shutdown coordination** — cancelling in-flight requests on shutdown; separate concern

---

## Design Options

### Option A: Decorator Hooks (Recommended)

**Approach**: Add `on_startup` and `on_shutdown` decorator methods to `App`, store callables in lists, run them during the ASGI lifespan protocol. Handle lifespan directly in `__call__` before delegating to `handle_request`.

**Implementation**:

```python
# src/chirp/app.py — new slots and init
__slots__ = (
    ...
    "_startup_hooks",
    "_shutdown_hooks",
)

def __init__(self, config=None):
    ...
    self._startup_hooks: list[Callable[[], Any]] = []
    self._shutdown_hooks: list[Callable[[], Any]] = []

# Decorator registration
def on_startup(self, func):
    """Register an async startup hook."""
    self._check_not_frozen()
    self._startup_hooks.append(func)
    return func

def on_shutdown(self, func):
    """Register an async shutdown hook."""
    self._check_not_frozen()
    self._shutdown_hooks.append(func)
    return func

# ASGI entry point
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        await self._handle_lifespan(scope, receive, send)
        return
    # ... existing HTTP handling ...

# Lifespan handler
async def _handle_lifespan(self, scope, receive, send):
    self._ensure_frozen()  # Freeze at startup, not first request

    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            try:
                for hook in self._startup_hooks:
                    result = hook()
                    if inspect.isawaitable(result):
                        await result
                await send({"type": "lifespan.startup.complete"})
            except Exception as exc:
                await send({
                    "type": "lifespan.startup.failed",
                    "message": str(exc),
                })
                return
        elif message["type"] == "lifespan.shutdown":
            for hook in self._shutdown_hooks:
                result = hook()
                if inspect.isawaitable(result):
                    await result
            await send({"type": "lifespan.shutdown.complete"})
            return
```

**Pros**:
- Matches chirp's existing decorator pattern (`@app.route`, `@app.error`, `@app.template_filter`)
- Matches the API already used in `examples/rag_demo/app.py:97-122`
- Simple and approachable — no new concepts for users
- Supports both sync and async hooks via `inspect.isawaitable`

**Cons**:
- Startup/shutdown are separate lists — no guarantee that cleanup mirrors setup
- Cannot share resources between startup and shutdown without app-level state

**Estimated Effort**: 3–4 hours

---

### Option B: Context Manager Lifespan

**Approach**: A single `@app.lifespan` context manager that wraps the server's lifetime. Code before `yield` runs at startup, code after runs at shutdown.

**Implementation**:

```python
@app.lifespan
async def lifespan(app):
    db = await create_pool()
    yield {"db": db}  # available in app state
    await db.close()
```

**Pros**:
- Cleanup is guaranteed (finally/exit semantics)
- Natural for resource management patterns
- Can inject startup state into requests

**Cons**:
- New concept not used elsewhere in chirp
- Doesn't match the `@app.on_startup`/`@app.on_shutdown` API already used in rag_demo
- More complex implementation (state injection, context management)
- Only one lifespan handler per app (vs. multiple startup/shutdown hooks)

**Estimated Effort**: 5–6 hours

---

### Option C: Both (Decorators + Context Manager)

**Approach**: Implement decorator hooks (Option A) as the primary API. Later add context-manager support as an advanced alternative.

**Pros**:
- Maximum flexibility
- Backwards compatible when adding the context manager later

**Cons**:
- Two ways to do the same thing from day one creates confusion
- Not needed yet — no user request for context manager API

**Estimated Effort**: 7–8 hours

---

## Recommended Approach

**Recommendation**: Option A (Decorator Hooks)

**Reasoning**:
1. The API is already designed and used in `examples/rag_demo/app.py:97-122` — this implements what users already expect
2. Matches every other registration pattern in chirp: `@app.route`, `@app.error`, `@app.template_filter`, `@app.template_global` — all decorators stored in lists, compiled at freeze time
3. The context manager API (Option B) can be added in a future RFC without breaking changes
4. Solves all five pain points identified in the problem statement

**Trade-offs accepted**:
- No built-in resource scoping (startup/shutdown not paired) — mitigated by module-level variables and the `Database` async context manager pattern already in use

---

## Architecture Impact

| Subsystem | Impact | Changes |
|-----------|--------|---------|
| `src/chirp/app.py` | **High** | New slots, `on_startup`/`on_shutdown` decorators, `_handle_lifespan` method, `__call__` lifespan branch |
| `src/chirp/server/handler.py` | **Low** | Remove `scope["type"] != "http"` guard (lifespan now handled before dispatch) |
| `src/chirp/testing/client.py` | **Medium** | `__aenter__` runs startup hooks, `__aexit__` runs shutdown hooks |
| `src/chirp/__init__.py` | **None** | No new public exports needed (decorators are methods on `App`) |
| `tests/` | **Medium** | New unit tests for lifespan protocol, update integration tests for TestClient |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Startup hook raises, server fails to start | Medium | High | Send `lifespan.startup.failed` with error message; pounce already handles this |
| Shutdown hook hangs | Low | Medium | Pounce has `shutdown_timeout` (default 10s); consider adding timeout to chirp too |
| Async hooks called from sync context | Low | Low | `_handle_lifespan` is async; use `inspect.isawaitable` for sync/async flexibility |
| TestClient skips lifespan in existing tests | Medium | Low | Existing tests have no hooks registered — `__aenter__` runs empty list, no behavior change |

---

## Open Questions

- [x] Should `_freeze()` move entirely to lifespan startup? **Yes** — it eliminates first-request latency and the thread-safety race. When no lifespan is used (bare ASGI server without lifespan support), the existing `_ensure_frozen()` in `__call__` remains as a fallback.
- [ ] Should shutdown hooks run in reverse registration order? (Python `atexit` does this; Starlette does not.)
- [ ] Should we log a warning when startup hooks are registered but the server doesn't send lifespan events?

---

## Implementation Plan

### Phase 1: Core Lifespan Protocol
- Add `_startup_hooks` and `_shutdown_hooks` slots and lists to `App`
- Add `on_startup` and `on_shutdown` decorator methods
- Implement `_handle_lifespan()` with proper ASGI protocol handling
- Branch on `scope["type"]` in `__call__` before `handle_request`

### Phase 2: Freeze Migration
- Call `_ensure_frozen()` at the start of `_handle_lifespan` startup
- Keep `_ensure_frozen()` in `__call__` for HTTP as a safe fallback

### Phase 3: TestClient Update
- `__aenter__`: freeze app + run startup hooks
- `__aexit__`: run shutdown hooks
- Ensure existing tests remain green

### Phase 4: Tests
- Unit: lifespan protocol (startup complete, startup failed, shutdown complete)
- Unit: silent return from server without lifespan (fallback path)
- Unit: multiple hooks, ordering, sync and async hooks
- Integration: TestClient with startup/shutdown hooks
- Integration: rag_demo example validation

**Estimated Total Effort**: 3–4 hours

---

## References

- **Pounce fix**: `pounce/asgi/lifespan.py` — `_run_app()` now handles silent returns in `finally`
- **ASGI Lifespan Spec**: https://asgi.readthedocs.io/en/latest/specs/lifespan.html
- **Existing API usage**: `examples/rag_demo/app.py:97-122` — `@app.on_startup` / `@app.on_shutdown`
- **Database lifecycle**: `src/chirp/data/database.py:189-229` — `connect()`/`disconnect()` methods
- **Dashboard workaround**: `examples/dashboard/app.py:87` — module-level `_seed_readings()` call

# RFC: Per-Worker Lifecycle Hooks

**Status**: Draft
**Date**: 2026-02-08
**Scope**: `chirp/app.py`
**Depends on**: Pounce RFC — Per-Worker Lifecycle Scopes

---

## Problem

Chirp's `@app.on_startup` and `@app.on_shutdown` hooks run during ASGI lifespan — once, on the main thread's event loop. Under pounce multi-worker, each worker runs its own asyncio event loop. Async resources created in `on_startup` (httpx clients, DB pools) bind to the lifespan loop and fail with `RuntimeError` when used from a worker loop.

### Evidence

**Hooks fire during lifespan, not per-worker:**

```
src/chirp/app.py:253-258 — startup hooks run inside _handle_lifespan()
src/chirp/app.py:267-271 — shutdown hooks run inside _handle_lifespan()
```

**The hackernews example demonstrates the problem:**

```
examples/hackernews/app.py:232 — httpx.AsyncClient created in on_startup
examples/hackernews/app.py:153 — worker uses client → RuntimeError (wrong loop)
```

### Impact

Every chirp app using async per-worker resources under pounce multi-worker needs this. The current workaround (per-event-loop dict with `id(loop)` keying and locks) works but has no cleanup path and requires boilerplate in every app.

---

## Goals

1. Provide `@app.on_worker_startup` and `@app.on_worker_shutdown` decorators that run on each worker's event loop.
2. No coupling to pounce — hooks dispatch from standard ASGI scope types that any server can send.
3. Consistent with chirp's existing decorator registration patterns.
4. Apps that don't use worker hooks are unaffected.

### Non-Goals

- Worker-scoped dependency injection or state container (apps manage their own state).
- Worker identification in request context (separate concern).
- Changes to the existing `on_startup` / `on_shutdown` hooks (they remain global lifespan hooks).

---

## Design

### Registration

```python
@app.on_worker_startup
async def create_client():
    _client_var.set(httpx.AsyncClient(base_url=API_URL, timeout=10.0))

@app.on_worker_shutdown
async def close_client():
    client = _client_var.get(None)
    if client:
        await client.aclose()
```

Hooks are stored in `_worker_startup_hooks` and `_worker_shutdown_hooks` lists, following the same pattern as `_startup_hooks` / `_shutdown_hooks`.

### Dispatch

In `App.__call__()`, check for `pounce.worker.startup` and `pounce.worker.shutdown` scope types:

```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        await self._handle_lifespan(scope, receive, send)
        return

    if scope["type"] == "pounce.worker.startup":
        await self._handle_worker_startup()
        return

    if scope["type"] == "pounce.worker.shutdown":
        await self._handle_worker_shutdown()
        return

    # ... existing HTTP handling ...
```

### Hook execution

```python
async def _handle_worker_startup(self) -> None:
    for hook in self._worker_startup_hooks:
        result = hook()
        if inspect.isawaitable(result):
            await result

async def _handle_worker_shutdown(self) -> None:
    for hook in self._worker_shutdown_hooks:
        result = hook()
        if inspect.isawaitable(result):
            await result
```

Errors in startup hooks propagate to pounce (which prevents the worker from accepting connections). Errors in shutdown hooks are caught and logged (cleanup failures shouldn't prevent worker exit).

---

## Architecture Impact

| File | Impact | Changes |
|------|--------|---------|
| `src/chirp/app.py` | **Medium** | New slots, decorators, `__call__` branches, handler methods |
| `tests/test_app.py` | **Medium** | New test class for worker lifecycle hooks |
| Examples | **Low** | hackernews example refactored to use new hooks |

No changes to routing, middleware, templating, or the existing lifespan protocol.

---

## Implementation Plan

### Phase 1: Registration (`app.py`)

- Add `_worker_startup_hooks` and `_worker_shutdown_hooks` to `__slots__` and `__init__`
- Add `on_worker_startup` and `on_worker_shutdown` decorator methods (same pattern as `on_startup`)

### Phase 2: Dispatch (`app.py`)

- Add scope type checks in `__call__` for `pounce.worker.startup` and `pounce.worker.shutdown`
- Implement `_handle_worker_startup()` and `_handle_worker_shutdown()`

### Phase 3: Tests (`tests/test_app.py`)

- Registration: hooks stored correctly, order preserved, frozen check
- Dispatch: app responds to worker scope types, hooks execute on call
- Error handling: startup raises propagate, shutdown errors are non-fatal

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Developer confuses `on_startup` with `on_worker_startup` | Medium | Clear docstrings explaining global vs per-worker semantics |
| Non-pounce servers never send worker scopes | Expected | Hooks simply never fire — apps work fine without them |
| Worker shutdown hooks called without startup | Low | Apps should tolerate this (e.g., `_client_var.get(None)` pattern) |

---

## Open Questions

1. Should worker hooks be subject to the `_check_not_frozen()` guard? (Proposed: yes, consistent with all other decorators.)
2. Should `TestClient` simulate worker startup/shutdown? (Proposed: no — TestClient runs in a single loop so lifespan hooks suffice.)

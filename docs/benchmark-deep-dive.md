# Chirp Benchmark Deep Dive: Why Errors and Why Slow

Investigation into Chirp's benchmark results: request failures (5–23%) and slower CPU throughput vs FastAPI.

---

## 1. Root Cause: Sync Handlers Block the Event Loop

**Evidence:** `chirp/_internal/invoke.py` lines 35–37

```python
result = handler(*args, **kwargs)
if inspect.isawaitable(result):
    result = await result
return result
```

Chirp calls sync handlers **directly** — no `asyncio.to_thread.run_sync()` or `anyio.to_thread.run_sync()`. When a sync handler does CPU-bound work (e.g. 50k hash iterations), it **blocks the entire asyncio event loop** of that worker.

**Architecture:**
- Pounce: N workers = N threads (3.14t) or N processes (GIL)
- Each worker: 1 event loop, 1 thread
- Sync handler runs in-place → blocks that worker's loop
- Other workers continue, but each worker handles only one request at a time for CPU-bound work

**Impact:** With 10 workers and ~30ms CPU per request, theoretical max ≈ 333 req/s. We see ~311 — close to the ceiling. FastAPI uses `run_in_executor` for sync `def` handlers, so it doesn't block the event loop and can handle more concurrent requests per worker.

---

## 2. Why Request Failures (503, Timeout, Reset)

### 2a. Request Queue 503s

**Evidence:** `pounce/_request_queue.py` — when `queue.acquire()` returns `False`, the wrapper sends 503.

Chirp benchmark app has `request_queue_enabled=True`, `request_queue_max_depth=2000`. With 100 concurrent clients and 2000 requests, bursts can fill the queue. When the semaphore is exhausted, new requests get 503.

### 2b. Connection / Read Timeout

**Evidence:** `pounce/worker.py` — `request_timeout` (default 30s) applies to body reads. `chirp/server/production.py` passes `request_timeout=30.0`.

For CPU workload: 100 concurrent clients × slow responses → connections can queue. If the client's `httpx` timeout (30s) fires before the server responds, we see failures. Under load, some requests may exceed 30s.

### 2c. Connection Refused / Reset

During startup, the benchmark may hit the server before all 10 workers are ready. Warmup helps but doesn't eliminate races. Under load, backpressure (max_connections, queue full) can cause connection resets.

---

## 3. Why Chirp Is Slower Than FastAPI on CPU

| Factor | Chirp | FastAPI |
|--------|-------|---------|
| Sync handler dispatch | Runs in event loop (blocks) | `run_in_executor` (thread pool) |
| Concurrency per worker | 1 CPU-bound request at a time | Multiple via thread pool |
| Worker model | 10 workers, 1 loop each | 10 workers, 1 loop each |
| CPU-bound scaling | Limited by workers | Better via executor threads |

FastAPI (Starlette) runs sync `def` handlers in a thread pool via `run_in_executor`, so the event loop stays responsive. Chirp runs them inline, so each CPU-bound request monopolizes its worker.

---

## 4. Optimization Opportunities

### 4.1. Run Sync Handlers in a Thread Pool (High Impact)

**File:** `chirp/_internal/invoke.py`

**Change:** Use `asyncio.to_thread.run_sync()` for sync handlers:

```python
async def invoke(handler: Any, *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(handler):
        return await handler(*args, **kwargs)
    # Sync handler — run in thread pool to avoid blocking event loop
    return await asyncio.to_thread.run_sync(
        lambda: handler(*args, **kwargs),
    )
```

**Caveat:** `inspect.iscoroutinefunction` catches `async def`. A sync function that returns a coroutine (e.g. `def f(): return some_async_fn()`) would be misclassified; that pattern is rare in Chirp handlers.

**Alternative:** Use `anyio.to_thread.run_sync` for consistency with Chirp's anyio usage (SQLite, streaming).

### 4.2. Disable Request Queue for Benchmarks (Low Impact)

The request queue can cause 503s under burst. For benchmarks, `request_queue_enabled=False` avoids that. For production, the queue is useful; the real fix is not blocking the loop (4.1).

### 4.3. Increase Client Timeout (Diagnostic)

If failures are timeouts, raising the benchmark client timeout (e.g. 60s) would reduce false failures. Doesn't fix the underlying slowness.

### 4.4. Tune Worker Count

More workers can improve CPU throughput, but with blocking handlers the gain is linear. The main win is 4.1.

---

## 5. Summary

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Request failures | Queue 503s, timeouts, connection resets under load | 4.1 + optionally 4.2 |
| Slow CPU throughput | Sync handlers block event loop | 4.1 — run sync in thread pool |
| JSON parity | JSON is fast; blocking less visible | 4.1 still helps under concurrency |

**Recommended first step:** Implement 4.1 (sync handlers in thread pool) in `chirp/_internal/invoke.py`. This should reduce failures and improve CPU throughput.

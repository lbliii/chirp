# Chirp Benchmark Deep Dive: Why Errors and Why Slow

Investigation into Chirp's benchmark results: request failures (5–23%) and slower CPU throughput vs FastAPI.

---

## 1. Sync Handler Strategy (Resolved)

**Current behavior:** `chirp/_internal/invoke.py` runs sync handlers via `asyncio.to_thread()` so they do not block the event loop. CPU-bound work is offloaded to a thread pool.

**Architecture:**
- Pounce: N workers = N threads (3.14t) or N processes (GIL)
- Each worker: 1 event loop, 1 thread
- Sync handler runs in thread pool → event loop stays responsive
- Other workers continue; concurrent requests per worker handled via executor

---

## 2. Why Request Failures (503, Timeout, Reset)

### 2a. Request Queue 503s (Mitigated)

**Evidence:** `pounce/_request_queue.py` — when `queue.acquire()` returns `False`, the wrapper sends 503.

The benchmark app now uses `request_queue_enabled=False` to avoid 503s under burst. For production, the queue is useful; benchmarks use a normalized config for fair comparison.

### 2b. Connection / Read Timeout

**Evidence:** `pounce/worker.py` — `request_timeout` (default 30s) applies to body reads. `chirp/server/production.py` passes `request_timeout=30.0`.

For CPU workload: 100 concurrent clients × slow responses → connections can queue. If the client's `httpx` timeout (30s) fires before the server responds, we see failures. Under load, some requests may exceed 30s.

### 2c. Connection Refused / Reset

During startup, the benchmark may hit the server before all 10 workers are ready. Warmup helps but doesn't eliminate races. Under load, backpressure (max_connections, queue full) can cause connection resets.

---

## 3. Why Chirp May Differ From FastAPI on CPU

| Factor | Chirp | FastAPI |
|--------|-------|---------|
| Sync handler dispatch | `asyncio.to_thread()` (thread pool) | `run_in_executor` (thread pool) |
| Concurrency per worker | Multiple via executor | Multiple via executor |
| Worker model | 10 workers, 1 loop each | 10 workers, 1 loop each |
| CPU-bound scaling | Via executor threads | Via executor threads |

Both frameworks now offload sync handlers to a thread pool. Benchmarks use a shared httpx.Client for connection pooling so the harness measures server performance, not client setup churn.

---

## 4. Optimization Opportunities

### 4.1. Sync Handlers in Thread Pool (Done)

**File:** `chirp/_internal/invoke.py` — uses `asyncio.to_thread()` for sync handlers.

### 4.2. Disable Request Queue for Benchmarks (Done)

**File:** `benchmarks/apps/chirp_app.py` — `request_queue_enabled=False` for benchmark runs.

### 4.3. Shared Client for Load Test (Done)

**File:** `benchmarks/run.py` — single `httpx.Client` with connection pooling; avoids measuring client setup/teardown per request.

### 4.4. Further Optimizations

- Compile handler dispatch metadata at freeze time (avoid `inspect.signature` per request)
- Fast JSON path (dict/list → bytes without str round-trip)
- Lazy request parsing (query, cookies, request_id from scope)

---

## 5. Summary

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Request failures | Queue 503s, timeouts, connection resets under load | 4.2 — disable queue for benchmarks |
| Slow CPU throughput | (was) Sync handlers block event loop | 4.1 — run sync in thread pool (done) |
| Client setup churn | Per-request httpx.Client creation | 4.3 — shared client with pooling (done) |

**Measurement methodology:** The harness uses a single shared `httpx.Client` so connection setup/teardown is not measured as server latency. Benchmarks reflect server performance, not client overhead.

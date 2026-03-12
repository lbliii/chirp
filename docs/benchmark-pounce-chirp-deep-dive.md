# Pounce + Chirp Connection Handling Deep Dive

Investigation into why a shared httpx.Client causes ~10x throughput drop for Chirp but not FastAPI/Flask. Focus: connection flow, keep-alive, and potential bottlenecks.

---

## 1. Architecture Overview

```
[Client: 100 threads, 1 shared httpx.Client]
         │
         │ 100 concurrent connections (or pool-limited)
         ▼
[Pounce: 10 workers, each with 1 event loop]
         │
         │ SO_REUSEPORT (Linux) or shared socket (macOS)
         │ Each worker: asyncio.start_server() → _handle_connection per connection
         ▼
[Chirp: ASGI app, stateless per request]
         │
         │ handle_request(scope, receive, send)
         ▼
[Response]
```

---

## 2. Pounce: Connection and Request Flow

### 2.1 Worker Model

| File | Lines | Behavior |
|------|-------|----------|
| `pounce/supervisor.py` | 88-102 | Spawns N workers as **threads** (nogil/3.14t) or **processes** (GIL) |
| `pounce/worker.py` | 214-305 | One event loop per worker; `asyncio.run(self._serve())` |
| `pounce/net/listener.py` | 78-97 | SO_REUSEPORT: each worker gets own socket; kernel distributes connections |

### 2.2 Connection Acceptance

| File | Lines | Behavior |
|------|-------|----------|
| `pounce/worker.py` | 246-251 | `asyncio.start_server()` calls `_handle_connection` on each accepted connection |
| `pounce/worker.py` | 377-396 | **Connection backpressure**: `_max_connections > 0` and `_active_connections >= _max_connections` → 503 |
| `pounce/worker.py` | 398 | `_active_connections += 1` per connection |

### 2.3 HTTP/1.1 Keep-Alive Loop

| File | Lines | Behavior |
|------|-------|----------|
| `pounce/worker.py` | 556-594 | `while True`: read, parse, dispatch, repeat |
| `pounce/worker.py` | 559-564 | `read_timeout = header_timeout` (first) or `keep_alive_timeout` (between requests) |
| `pounce/worker.py` | 561-564 | `data = await asyncio.wait_for(reader.read(65536), timeout=read_timeout)` |
| `pounce/worker.py` | 578 | `events = proto.receive_data(data)` — one `h11.Connection` per connection, reused |
| `pounce/worker.py` | 584-594 | `_process_events(events)` → `_handle_request`; `awaiting_headers = False` after first request |
| `pounce/worker.py` | 443-451 | `proto.start_new_cycle()` after each request |

**Key**: One async task per connection. Connection stays open; `reader`/`writer` and `H1Protocol` are reused across requests.

### 2.4 Request → ASGI

| File | Lines | Behavior |
|------|-------|----------|
| `pounce/worker.py` | 666-675 | `build_scope()`; `scope["extensions"]["request_id"]` |
| `pounce/worker.py` | 731-764 | Bodyless: `create_disconnect_receive(disconnect)`; body: `create_receive_with_disconnect(body_queue, disconnect)` |
| `pounce/worker.py` | 766-778 | `create_send(proto, writer, send_state, ...)` |
| `pounce/worker.py` | 797-824 | `_run_with_disconnect_monitor` or `_run_with_body_reader` → `await app(scope, receive, send)` |
| `pounce/worker.py` | 864-865 | `await writer.drain()` after response |

### 2.5 ASGI Bridge (Send)

| File | Lines | Behavior |
|------|-------|----------|
| `pounce/asgi/bridge.py` | 251-258 | `_COALESCE_THRESHOLD = 16KB`; `_DRAIN_THRESHOLD = 64KB` |
| `pounce/asgi/bridge.py` | 277-281 | Write coalescing: hold head + first body chunk, single `write()` when ≤16KB |
| `pounce/asgi/bridge.py` | 331-334 | Back-pressure: drain when buffer > 64KB |
| `pounce/asgi/bridge.py` | 374-381 | Auto-inject `Transfer-Encoding: chunked` when no Content-Length |

---

## 3. Chirp: Request Handling

### 3.1 Entry Point

| File | Lines | Behavior |
|------|-------|----------|
| `chirp/server/handler.py` | 55 | `Request.from_asgi(scope, receive)` |
| `chirp/server/handler.py` | 78-99 | `match = router.match()`; `_invoke_handler()` |
| `chirp/server/handler.py` | 99 | `response = await handler(request)` |
| `chirp/server/handler.py` | 134 | `send_response(response, send)` |

### 3.2 Request Body

| File | Lines | Behavior |
|------|-------|----------|
| `chirp/http/request.py` | 108-118 | `body()`: cached in `_cache["_body"]` |
| `chirp/http/request.py` | 121-129 | `stream()`: `await self._receive()` until `more_body=False` |
| `chirp/server/handler.py` | 165-169 | `_read_body_if_needed_from_plan()` — only for GET/HEAD skip; POST/PUT/PATCH read body |

### 3.3 Response

| File | Lines | Behavior |
|------|-------|----------|
| `chirp/server/sender.py` | 23-50 | `send_response()`: `http.response.start` + `http.response.body` with Content-Length |
| `chirp/server/negotiation.py` | 326-331 | dict/list: `json.dumps().encode("utf-8")` → bytes |

---

## 4. Paths That Differ: Connection Reuse vs New

### Per-Connection State (Pounce)

| State | Reused? | Location |
|-------|---------|----------|
| `reader` / `writer` | Yes | `worker.py:343` |
| `H1Protocol` (h11.Connection) | Yes | `worker.py:372` — `proto.start_new_cycle()` between requests |
| `request_count` | Yes | Per-connection counter |

### Per-Request State

| State | Reused? | Location |
|-------|---------|----------|
| ASGI scope | No | `worker.py:667` |
| `receive` / `send` | No | `worker.py:759` |
| `body_queue` | No | `worker.py:738` |
| `disconnect` Event | No | `worker.py:731` |

**Chirp**: No connection state. Each request is independent. `Request.from_asgi()` is stateless.

---

## 5. Potential Bottlenecks

### 5.1 Client-Side (httpx)

| Hypothesis | Evidence |
|------------|----------|
| **Connection pool limit** | httpx default `max_connections` may be low (e.g. 10). With 100 threads, 90 block waiting for a connection. |
| **Lock contention** | 100 threads sharing one client → contention on pool acquire/release. |
| **Thread vs async** | httpx Client is sync; 100 threads block. With 10 workers, server can handle 10 concurrent. If client only has 4 connections, client becomes bottleneck. |

**Test**: Use `httpx.Limits(max_connections=100, max_keepalive_connections=100)` with shared client. If throughput improves, pool limit was the cause.

### 5.2 Pounce-Side

| File | Lines | Potential Issue |
|------|-------|-----------------|
| `worker.py` | 864-865 | `writer.drain()` — blocks until TCP buffer is flushed. Slow client could stall. |
| `bridge.py` | 331-334 | Back-pressure drain when buffer > 64KB — small JSON responses unlikely to hit this. |
| `worker.py` | 417-419 | Timeout switch: `header_timeout` vs `keep_alive_timeout` — no obvious issue. |
| `worker.py` | 380-396 | Connection backpressure 503 — if `max_connections` is hit, new connections rejected. |

### 5.3 Chirp-Side

| File | Lines | Potential Issue |
|------|-------|-----------------|
| `handler.py` | 55 | `Request.from_asgi()` — parses headers, query, cookies. Same for new vs reused. |
| `handler.py` | 165-169 | Body read — GET/HEAD skip; POST reads. Benchmark uses GET. |
| `invoke.py` | 44 | `asyncio.to_thread()` for sync handlers — adds thread-pool hop. |

### 5.4 Socket Distribution (macOS)

| File | Lines | Behavior |
|------|-------|----------|
| `listener.py` | 98-100 | **SO_REUSEPORT unavailable** (macOS): one shared socket, all workers accept from it. |
| `listener.py` | 78-97 | SO_REUSEPORT (Linux): each worker has own socket. |

On macOS, one socket + 10 workers → all workers compete on `accept()`. With 100 connections, distribution may be uneven. Not obviously connection-reuse specific.

---

## 6. Why FastAPI/Flask Weren't Affected

| Framework | Server | Worker Model |
|-----------|--------|--------------|
| Chirp | Pounce | 10 threads, 1 event loop each |
| FastAPI | Uvicorn | 10 processes (or async workers) |
| Flask | Gunicorn | 10 sync worker processes |

**Hypothesis**: If the bottleneck is client-side (httpx pool limit), all servers would be affected equally — the client can only send N requests at a time. But we observed Chirp 66 req/s vs FastAPI 2348 req/s with the same harness. So the bottleneck is **server-side**: Chirp/Pounce is slower to respond, and when the client is connection reuse, something about that interaction causes Chirp to be especially slow.

**Alternative**: With per-request clients, each request opens a new connection. The kernel distributes 2000 connections across 10 workers. With shared client, we have 100 persistent connections. Maybe Pounce's connection handling behaves differently under 100 long-lived connections vs 2000 short-lived ones? E.g. connection table growth, event loop overhead per connection, etc.

---

## 7. Profiling Results (POUNCE_PROFILE=1)

Instrumentation added to Pounce worker (`pounce/_profile.py`). Run with:

```bash
PYTHONPATH=../pounce/src uv run python -m benchmarks.run chirp --profile --client shared-limits
```

**Findings (shared client, concurrency=100):**

| Phase | Avg (ms) | P99 (ms) | Verdict |
|-------|----------|----------|---------|
| read | 0.6–31 | 0.9–144 | **Bottleneck** — server blocks waiting for client |
| parse | 0.0–0.1 | — | Negligible |
| app | 0.3–6 | — | Fast |
| drain | 0.0 | 0.0 | Instant — not the bottleneck |

**Conclusion**: The slowdown is **read** — time spent in `reader.read()` waiting for the client to send the next request. `writer.drain()` is effectively instant. With 100 threads sharing one httpx client, client-side pool contention delays when the next request arrives. The server is idle; the client is the bottleneck.

---

## 8. Recommended Next Steps

1. ~~**Profile**~~ — Done. Read is the bottleneck; drain is not.
2. **Concurrency sweep**: Run shared client with CONCURRENCY=10, 50, 100. CONCURRENCY=10 matches workers and restores throughput.
3. **Pounce vs Uvicorn**: Chirp+Uvicorn handles shared client better — suggests Pounce's per-connection keep-alive loop interacts differently with client pool behavior.
4. **Connection count**: Log active connections per worker. With 100 connections and 10 workers, expect ~10 per worker. If skewed, investigate.

---

## 9. File Reference Summary

| Topic | File | Lines |
|-------|------|-------|
| Request profiling | `pounce/_profile.py` | — |
| Connection accept | `pounce/worker.py` | 343-396 |
| Keep-alive loop | `pounce/worker.py` | 556-594 |
| Request dispatch | `pounce/worker.py` | 665-865 |
| ASGI send | `pounce/asgi/bridge.py` | 261-339 |
| Chirp handler | `chirp/server/handler.py` | 33-135 |
| Chirp request | `chirp/http/request.py` | 108-213 |
| Chirp sender | `chirp/server/sender.py` | 23-50 |
| Socket strategy | `pounce/net/listener.py` | 78-100 |

# Bengal stack free-threading ledger

Status: published for Chirp issue [#944](https://github.com/lbliii/chirp/issues/944)
(epic [#941](https://github.com/lbliii/chirp/issues/941), saga
[#940](https://github.com/lbliii/chirp/issues/940)).

This ledger is the shared **shared-vs-isolated** map for Chirp, Kida, Pounce,
and in-tree Pelt on Python 3.14t with `PYTHON_GIL=0`. It records ownership
boundaries that already ship — not a throughput claim, and not a promise that
every application-owned object is race-free.

## Contract in one sentence

**Mutate shared warm state only at startup (or under an explicit lock); isolate
per-request / per-connection / per-render work so free-threaded workers may
share the warm snapshot without racing.**

## Shared vs isolated

| Class | Meaning | Stack examples |
| --- | --- | --- |
| **Shared warm (read-mostly)** | Built once before serving; many threads read concurrently | Chirp frozen `App` runtime / route trie / Kida `Environment`; Pounce frozen server config; Pelt built-in codec templates |
| **Isolated (task-owned)** | Private to one request, render, worker loop, or connection checkout | Chirp `ContextVar` (`g`, request); Kida `RenderContext`; Pounce per-request ASGI scope; Pelt checked-out connection + statement cache |
| **Shared mutable (locked)** | Truly cross-request writers; must take an explicit lock or publish atomically | Chirp caches / buses / registries; Pelt process-wide built-in codec registry; Pounce counters that cross workers |
| **App-owned (out of contract)** | Application or extension state Chirp did not create | Module-level dicts, unlocked caches, custom filters with globals, shared DB sessions |

## Startup-only mutation

Each project draws a hard line between **setup** and **serve**:

| Project | Setup (mutable) | Serve (stable) | Publication boundary |
| --- | --- | --- | --- |
| **Chirp** | Route/middleware/registry registration on a live `App` | Frozen runtime state, compiled trie, bound Kida env | `App._freeze()` under `_freeze_lock` (double-check); registration after freeze fails loud |
| **Kida** | `Environment` construction, loader/filter/global registration | Concurrent `render()` / `get_template()` against a configured env | Treat public configuration as startup-only; registries publish copy-on-write snapshots |
| **Pounce** | `Server` / config construction, lifespan startup before workers accept | Frozen shared config; per-worker loops and queues | Workers share the process; app must finish warm-state publication before multi-thread accept |
| **Pelt** | Module import, default codec registry build, pool construction | Exclusive checkout ownership; decode against immutable snapshots | Pool `acquire`/`release`; registry writers take a short lock and publish `MappingProxyType` snapshots |

**Ordered warm sequence** (Chirp freeze → Kida precompile /
`static_context` → Pelt pool + type warmup), aligned to Pounce
`pounce.worker.startup` / Chirp `@app.on_worker_startup`, lives in
[warm-state-startup-protocol.md](warm-state-startup-protocol.md) (#945).
That protocol owns cold-vs-warm RSS measurement notes for ≥4 workers and the
cross-link to [pounce#321](https://github.com/lbliii/pounce/issues/321); this
ledger owns shared-vs-isolated classification only.

After that boundary, **do not** mutate the warm snapshot from request threads
except through the locked or ownership-based paths named below.

## Per-project ledger

### Chirp

| Surface | Mode | Notes |
| --- | --- | --- |
| `AppConfig`, `Request`, compiled routes | Shared warm | Frozen dataclasses / immutable trie |
| `g`, `get_request()`, CSRF/auth ContextVars | Isolated | Per-request ContextVar |
| Template `Environment` | Shared warm | Created once in `_freeze()` |
| Caches, ReactiveBus, OOB/signal registries | Shared mutable | Explicit `threading.Lock` |
| App / domain registration | Startup-only | `RuntimeError` after freeze |
| Application module globals | App-owned | Outside Chirp's contract |

Published guidance:
[Thread Safety](https://lbliii.github.io/chirp/docs/about/thread-safety/).

### Kida

| Surface | Mode | Notes |
| --- | --- | --- |
| Configured `Environment` | Shared warm | Startup-only configuration |
| Filter / test / global registries | Shared warm (COW) | Copy-on-write publication; serialize writers if registering at runtime |
| `RenderContext` | Isolated | ContextVar per `render()` |
| Built-in loaders | Shared warm reads | Concurrent reads when configured sources are stable; do not mutate loader lists while workers read |
| Custom filters touching globals | App-owned | Caller must lock |

Published guidance:
[Kida Thread Safety](https://lbliii.github.io/kida/docs/about/thread-safety/).

### Pounce

| Surface | Mode | Notes |
| --- | --- | --- |
| Server configuration | Shared warm | Frozen / read-only across thread workers |
| Per-request ASGI scope / receive / send | Isolated | Never shared across workers |
| Per-worker event loop + queues | Isolated (per worker) | Event loops are not thread-safe |
| Connection / backpressure counters | Shared mutable or per-worker | Internals are lock-guarded or worker-local |
| ASGI application globals | App-owned | Same free-threading rules as Chirp apps |

Published guidance:
[Pounce Thread Safety](https://lbliii.github.io/pounce/docs/about/thread-safety/).

### Pelt (in-tree `chirp.data.drivers._pelt`)

| Surface | Mode | Notes |
| --- | --- | --- |
| Built-in codec registry templates | Shared warm / locked writes | Process-wide; writers lock; readers use snapshots |
| Type-catalog metadata cache | Shared warm (immutable after publish) | Keyed by host/port/database; pool create acquires; invalidate on last pool close / `reset_type_catalog` |
| Pool | Shared coordinator | Exclusive checkout; reset completes before republication |
| Checked-out connection | Isolated | Protocol, prepared-statement cache, dynamic OID ledger are connection-local |
| Parallel row decode | Isolated workers | Fans out only when GIL is off and row/cell thresholds are met |

Evidence map:
[docs/pelt-free-threading.md](../pelt-free-threading.md). Applications use
`chirp.data.Database`, not private `_pelt` imports.

## Honest boundaries

These are **out of** the stack ledger promise:

1. **App-owned mutable context** — anything the application stores in module
   globals, unlocked caches, or custom template callables remains the app's
   responsibility.
2. **Loader / source mutation under traffic** — changing Kida loader lists,
   template files behind a non-reloading loader, or Chirp template dirs while
   workers serve is unsupported unless a documented reload path owns it.
3. **Shared PostgreSQL connections** — never share one live Pelt connection
   across threads; checkout grants exclusive ownership. Saga #940 lists this as
   an explicit non-goal.
4. **SSE / Suspense identity snapshots** — Chirp pins request/auth context at
   connect or negotiation time; mid-stream logout does not rewrite the
   snapshot until reconnect / `kick_user`.
5. **C extensions that re-enable the GIL** — a single GIL-owning extension
   serializes the process; the ledger assumes PEP 703 `_Py_mod_gil = 0`
   declarations on Chirp/Kida/Pelt paths.
6. **Throughput** — overlap and ownership proofs are correctness receipts, not
   capacity claims. Public scaling numbers require schema-validated artifacts
   (#947), not this ledger.

## Integration proof

Chirp hosts a stack glue test under free-threading:

- File: `tests/interop/test_free_threading_stack.py`
- Marker: `@pytest.mark.issue(944)`
- Path: Chirp `App` → Pelt `Pool` checkout → Kida `Template` render → Pounce
  `TestServer` HTTP GET
- Gate: skips unless `Py_GIL_DISABLED` and `sys._is_gil_enabled() is False`
  (CI sets `PYTHON_GIL=0` on the free-threaded job)

The pool uses the real Pelt `Pool` class with probe connections so the default
CI job (no Postgres service) still exercises exclusive checkout + release
ordering. Live wire I/O and parallel decode remain covered by
`data-pg-gil-gate` / `test-postgres` and
[docs/pelt-free-threading.md](../pelt-free-threading.md).

## Sibling doc links

| Project | Thread-safety doc | Ledger link |
| --- | --- | --- |
| Chirp | `site/content/docs/about/thread-safety.md` | Links here |
| Pelt (in Chirp) | `docs/pelt-free-threading.md` | Links here |
| Kida | https://lbliii.github.io/kida/docs/about/thread-safety/ | Reciprocal link tracked with epic #941 sibling repos |
| Pounce | https://lbliii.github.io/pounce/docs/about/thread-safety/ | Reciprocal link tracked with epic #941 sibling repos |

Warm-state ordering (not ownership classification):
[warm-state-startup-protocol.md](warm-state-startup-protocol.md). Pounce-side
hook documentation is tracked in
[pounce#321](https://github.com/lbliii/pounce/issues/321) (out of this repo).

This Chirp leaf publishes the ledger and Chirp/Pelt inbound links. Kida and
Pounce retain their own thread-safety pages; pointing those pages at this
ledger is sibling-repo work so Chirp does not silently edit foreign trees.

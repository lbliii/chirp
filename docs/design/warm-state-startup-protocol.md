# Cross-stack warm-state startup protocol

Status: design for Chirp issue [#945](https://github.com/lbliii/chirp/issues/945)
(epic [#941](https://github.com/lbliii/chirp/issues/941), saga
[#940](https://github.com/lbliii/chirp/issues/940)).

Companion ownership map:
[free-threading stack ledger](free-threading-stack-ledger.md).

This note defines the **ordered warm sequence** apps should finish before
accepting production traffic under multi-worker Pounce. It is an operator and
integrator contract, not a throughput claim and not a promise that every
application-owned object is race-free.

## Contract in one sentence

**Publish shared warm state once in order (Chirp freeze → Kida compile /
`static_context` → Pelt pool + type warmup), using Pounce's
`pounce.worker.startup` scope as the canonical per-worker hook when that scope
is emitted; never share a live PostgreSQL connection across threads.**

## Canonical hook

| Layer | Surface | Role |
| --- | --- | --- |
| **Pounce** | ASGI scope `type == "pounce.worker.startup"` | Canonical server-emitted warm point per worker that receives the scope |
| **Chirp** | `@app.on_worker_startup` | App-facing registration; Chirp dispatches the scope to registered hooks |
| **App** | Hook body | Runs the warm steps below that belong to the worker / process |

Pounce owns when the scope is sent. Chirp owns dispatch into
`@app.on_worker_startup` / `@app.on_worker_shutdown` (see
`LifecycleCoordinator.handle_worker_startup` and the production deploy guide).
Apps own what to warm.

### Sibling-repo docs (out of tree)

Pounce documents the server-side hook under
[pounce#321](https://github.com/lbliii/pounce/issues/321)
(*Document `pounce.worker.startup` as canonical warm-state hook*). That work
lives in the Pounce repository; Chirp cannot land it here.

**Expected Pounce link targets** (once #321 ships — verify against the live
tree before citing as published):

- Design / worker docs that name `pounce.worker.startup` as the warm hook, for
  example `docs/design/warm-state-startup.md` or the worker lifecycle section of
  `docs/design/core-contract.md`.
- Reciprocal link back to this Chirp protocol:
  `https://github.com/lbliii/chirp/blob/main/docs/design/warm-state-startup-protocol.md`

Until those pages exist, treat pounce#321 as the tracking issue and this file as
the Chirp-side source of truth for ordering and ownership.

## Ordered warm sequence

Run these steps in order. Later steps may assume earlier ones have published
immutable (or lock-guarded) shared state.

```text
1. Chirp freeze
2. Kida precompile + static_context publication
3. Pelt pool construction + type / codec warmup
── then accept traffic ──
```

### 1. Chirp freeze

**Owner:** Chirp (`App._ensure_frozen` / `_freeze` under `_freeze_lock`).

**Publishes:** frozen `AppConfig`, compiled routes / hypermedia program, bound
Kida `Environment`, registries that refuse post-freeze mutation.

**When:** lifespan startup already calls `_ensure_frozen()` before
`@app.on_startup` hooks. `app.run()` / `app.freeze()` freeze explicitly. Worker
hooks must not register routes, middleware, filters, or other setup-time
mutation — freeze has already closed that door for a live app.

**Rule:** treat freeze as the hard setup→serve boundary from the
[stack ledger](free-threading-stack-ledger.md). Warm work after freeze may
*read* and *populate caches* that are designed for concurrent readers; it must
not reopen registration APIs.

### 2. Kida precompile / `static_context`

**Owner:** Chirp templating integration + Kida `Environment`; app supplies
constants and the template set to warm.

**`static_context`:** pass compile-time constants through
`AppConfig(static_context=...)`. Chirp freezes a mutable dict to
`MappingProxyType` and hands a copy into the Kida environment at freeze
(`create_environment`). Those values participate in Kida's partial evaluator —
they are startup-published, not per-request globals.

**Precompile:** after freeze, resolve hot templates through the bound
environment (for example `env.get_template(name)` for every template that
serves first-byte traffic). The goal is to pay parse/compile cost before the
first client request, not to invent a second template tree. Prefer the app's
real template names (pages, layouts, fragments) over synthetic strings.

**Where to run:**

- **Shared across thread workers in one process** — once after freeze
  (lifespan `@app.on_startup` or the first worker hook with an idempotent
  guard). Thread workers share the process-wide Kida env.
- **Isolated async / process workers** — inside `@app.on_worker_startup` when
  each worker has its own interpreter or must not assume a parent warm.

### 3. Pelt pool + type warmup

**Owner:** Chirp `Database` / in-tree Pelt pool; app chooses pool size and which
types/queries to warm.

**Pool construction:** create the pool (or call `Database.connect()`) so
connections exist before traffic. Pool size is an operator choice; this protocol
does not prescribe a formula.

**Type warmup:** on a **checked-out** connection, run the queries that populate
connection-local codec / OID discovery for types your app actually uses (or a
`SELECT 1` readiness probe if you only need connectivity). Release the
connection before serving. See
[docs/pelt-free-threading.md](../pelt-free-threading.md) for exclusive checkout
and connection-local registries.

**Where to run:**

- Prefer **one pool per process** (or per async worker event loop), never one
  live connection shared by many threads.
- Use `@app.on_worker_startup` when the pool or async client must bind to that
  worker's event loop (same rule as httpx clients in the deploy guide).
- Framework-managed `App(db=...)` already connects during lifespan startup; do
  not open a second process-wide pool "for warmth" unless you own its lifecycle.

## When `pounce.worker.startup` is emitted

Chirp's production posture today:

- Worker lifecycle hooks require production `worker_mode="async"` so Pounce
  emits `pounce.worker.startup` / `pounce.worker.shutdown`.
- On free-threaded Python, `worker_mode="auto"` resolves to **sync** thread
  workers, which **do not** emit those scopes. Chirp rejects launch if worker
  hooks are registered while the effective mode is sync.

So the canonical hook is still `pounce.worker.startup`, but apps that stay on
sync thread workers must warm shared state at **freeze + lifespan
`@app.on_startup`** instead of `@app.on_worker_startup`. Choosing
`worker_mode="async"` is the explicit path to the per-worker hook under
free-threading.

This is a lifecycle fact, not a scaling recommendation. Sync thread workers and
async workers solve different ownership problems; pick the mode that matches
where your warm resources live.

## Ownership boundaries

| Step | Mutates | Shared after warm? | Isolated forever |
| --- | --- | --- | --- |
| Chirp freeze | App registries → frozen runtime | Frozen app, route trie, Kida env | Per-request `ContextVar` / `Request` |
| Kida precompile / `static_context` | Template compile caches; env config at freeze | Compiled templates + frozen static_context | `RenderContext` per render |
| Pelt pool + type warmup | Pool membership; per-connection codec ledgers during checkout | Pool coordinator (checkout/release) | Checked-out connection + statement cache |
| App httpx / async clients | Client construction in worker hook | Usually **not** shared across workers | Per-worker `ContextVar` client |

## Non-goals

1. **No shared PostgreSQL connections** — never hand one live Pelt/psycopg/asyncpg
   connection to multiple threads. Checkout grants exclusive ownership; saga
   #940 lists this as an explicit non-goal.
2. **No public multicore / GIL-off capacity claims** — warming reduces first-request
   latency and RSS surprise; it does not authorize req/s or "N× cores" marketing.
   Schema-validated artifacts belong to separate proof work (#947), not this
   protocol.
3. **No second freeze API** — do not invent a parallel "warm()" framework entry
   that bypasses `_freeze_lock` publication.
4. **No fabricated request at startup** — hooks take no synthetic `Request`; warm
   plain functions with explicit parameters (Chirp's documented rule on
   `on_startup` / `on_worker_startup`).
5. **No requirement that every app use Postgres or Pelt** — skip step 3 when the
   app has no database; the ordering still applies to the steps you do run.
6. **No silent reliance on sync workers emitting worker scopes** — they do not
   today; see above.

## Example call sites (existing)

There is **no** `forum` or `changelog` scaffold in-tree that demonstrates the
full Chirp → Kida → Pelt warm sequence. Do not invent a fake example app for
this leaf.

Existing apps that already call the canonical Chirp hook (per-worker resources,
not the full three-step protocol):

| Example | Hook usage |
| --- | --- |
| `examples/standalone/hackernews/app.py` | `@app.on_worker_startup` / `@app.on_worker_shutdown` for per-worker `httpx.AsyncClient` |
| `examples/standalone/ollama/app.py` | Same pattern — client stored in a `ContextVar` |
| `examples/chirpui/rag_demo/app.py` | `@app.on_worker_startup` connects a per-worker `Database` |

**Intended call site** for the full protocol (illustrative, not a shipped
scaffold):

```python
from kida import Environment, FileSystemLoader

from chirp import App, AppConfig

HOT_TEMPLATES = ("layout.html", "index.html")

config = AppConfig(
    env="production",
    debug=False,
    worker_mode="async",  # required for pounce.worker.startup hooks
    static_context={"site_name": "Example"},
    # secret_key / workers / … as usual
)
# Retain an Environment you own so warm code does not reach through private
# App runtime fields. AppConfig.static_context is still applied when Chirp
# builds the default env; a custom env must set static_context itself.
env = Environment(
    loader=FileSystemLoader("templates"),
    static_context=dict(config.static_context or {}),
)
app = App(config, kida_env=env)


@app.on_worker_startup
async def warm_worker() -> None:
    # 1. Freeze already happened (lifespan / run). Do not register routes here.
    # 2. Kida precompile — real template names only
    for name in HOT_TEMPLATES:
        env.get_template(name)

    # 3. Pelt / Database — one pool or connection ownership per worker loop
    # db = Database(DATABASE_URL)
    # await db.connect()
    # async with db.connection() as conn:  # exclusive checkout
    #     await conn.execute("SELECT 1")   # connectivity / type touch
    # store db on a ContextVar; close in on_worker_shutdown
```

Wire shutdown symmetrically with `@app.on_worker_shutdown`. For sync thread
workers without the scope, move shared Kida precompile into `@app.on_startup`
and keep DB ownership checkout-based.

## Cold vs warm RSS spike notes (≥4 Pounce thread workers)

These notes are a **measurement recipe and qualitative expectation**, not a
capacity rating. Do not copy them into READMEs as "uses N× less memory" claims.

### What to measure

On Linux, prefer process `VmRSS` from `/proc/<pid>/status` (or
`ps -o rss=`). On macOS, `ps -o rss=` (KB) is adequate for a spike check. Record:

1. **Cold** — interpreter + imported modules + frozen app **before** Kida
   precompile and **before** pool connections exist (or immediately after freeze
   with warm steps skipped).
2. **Warm** — same process after completing steps 2–3 above.
3. **Workers** — Pounce configured with **at least 4** workers in the mode under
   test (`workers=4`). Note sync thread vs async explicitly; memory topology
   differs (threads share an address space; processes do not).

Capture GIL posture for the receipt: Python 3.14t with `PYTHON_GIL=0` when that
is the configuration under study. A GIL-enabled run is a different experiment.

### How to run a local spike (operator recipe)

```bash
# Example shape only — adjust module path and worker mode to the app under test.
PYTHON_GIL=0 pounce serve --app myapp:app --workers 4 --worker-mode async &
PID=$!
# Wait until /ready succeeds, then:
ps -o rss= -p "$PID"   # warm RSS after startup hooks
# Compare to a second boot with warm steps stubbed out, or sample RSS
# immediately after freeze before on_worker_startup work if you gate it.
```

For a tighter A/B, gate steps 2–3 behind an env flag (`CHIRP_SKIP_WARM=1`) so
cold and warm boots share the same code path otherwise.

### Honest expectations (not public numbers)

| Observation | Honest reading |
| --- | --- |
| Warm RSS ≥ cold RSS | Expected: compiled templates and live pool connections retain memory |
| Step 2 cost | Scales with **number and size of templates** precompiled, not with worker count inside one process |
| Step 3 cost | Scales with **pool size × connection footprint** (TLS buffers, codec ledgers); each connection is owned, not shared |
| 4 thread workers in one process | Threads share the warm snapshot; do not multiply template RSS by 4 inside that process |
| 4 process workers | Each process repeats warm RSS; budget roughly per-process warm size × worker count |
| First-request latency | Warm should move compile/connect cost off the first client; measure TTFB separately from RSS |

Publish only machine receipts (command, commit SHA, worker mode, GIL flag, cold
RSS, warm RSS) when you need evidence. This design doc intentionally omits
numeric ranges so stale laptop samples do not become marketing.

## Related links

| Document | Relationship |
| --- | --- |
| [free-threading-stack-ledger.md](free-threading-stack-ledger.md) | Shared-vs-isolated ownership map; links here for startup ordering |
| [pelt-free-threading.md](../pelt-free-threading.md) | Pelt checkout / codec evidence |
| Site deploy guide (`site/content/docs/quality/deployment/production.md`) | Operator entry; links here for warm-state ordering |
| Site thread safety (`site/content/docs/about/thread-safety.md`) | End-user free-threading model; points at the ledger |
| [pounce#321](https://github.com/lbliii/pounce/issues/321) | Pounce-side documentation of the canonical hook (out of repo) |

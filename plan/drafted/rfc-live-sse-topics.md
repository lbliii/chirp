# RFC: `live()` — SSE Topic Primitive (Declare-Once, Bind-Many)

**Status**: Partially implemented. The single-node primitive shipped as `signal()` (`@app.signal` / `@app.derived` / `app.emit` + `signal()` / `signal_block()` / `signal_connect()` globals + the `/_chirp/live` merge stream + `rules_signals` contract; `src/chirp/realtime/signals.py`, `signal_globals.py`, `signal_stream.py`), with Lucky Cat migrated onto one connection. The §1–11 design below predates that build and uses the pre-ship working name `live()`; the shipped surface is `signal()` (see §12 for the as-built names). **Section 12 (multi-worker `SignalBus` backplane + the pure-derived contract) is a NOT-NOW DESIGN — not implemented and not scheduled** (see the status banner at the head of §12). It is the opt-in production upgrade: a new `SignalBus` plugin protocol, a `signal_bus` `AppConfig` field + `set_signal_bus` setter (reusing the existing `chirp[redis]` extra), and a `signal_bus_single_worker` contract rule — all root `AGENTS.md` stop-and-ask surfaces. Must route through realtime, contracts, and app/state stewards before any backplane code lands. Stays in `plan/drafted/` until accepted.
**Date**: 2026-06-12
**Scope**: `src/chirp/realtime/`, `src/chirp/app/` (registry + state + compiler), `src/chirp/contracts/rules_sse.py` (+ a new `rules_live_topics.py`), `src/chirp/templating/macros/chirp/sse.html`, `examples/chirpui/lucky_cat/`
**Related**: `plan/drafted/rfc-shared-store.md` (Option C — SSE-broadcast store; this RFC supersedes that phase), `plan/drafted/epic-fragment-only-sse.md`, `plan/drafted/epic-reactive-phase2.md`, `pounce-0-7-adoption.md` (HTTP/2 transport), chirp issue **#238** (dead-ticker class)

---

## 1. Summary & Motivation

### The footgun: HTTP/1.1 caps connections, persistent SSE spends them

Browsers cap concurrent connections per origin at **~6 on HTTP/1.1**. That cap
is client-fixed — it is not tunable from Chirp or pounce. Each persistent Chirp
SSE scope (`sse_scope(url)` → one `EventStream` route) holds **one** connection
for the lifetime of the stream. An SSE-heavy app exhausts the budget fast.

Lucky Cat is the canonical victim. Its shell layout opens **two** always-on SSE
connections on every page (`examples/chirpui/lucky_cat/pages/_layout.html:647,652`):

```kida
{{ sse_scope("/notifications/stream", wrapper_class="luckycat-notif-sse") }}
{{ sse_scope("/ticker/stream", wrapper_class="luckycat-ticker-sse") }}
```

Per-page streams stack on top: a market detail page adds
`/markets/{symbol}/stream`, the trade tape adds `/ft/stream`. Reach four held
SSE connections plus the page's own boosted-navigation GET budget and the origin
hits the wall.

**Deterministic evidence.** Holding 4 SSE streams + the page's 2 app SSE = 6.
A fresh `GET /health` then **times out** — the browser has no free connection to
issue it. At 2 held streams the same `GET /health` returns in ~5ms. Under
boosted htmx navigation the nav GET has no free socket and **blocks** — the
symptom users report is "the app is stuck, won't navigate away." This recurs
across multiple Chirp apps because it is a **transport-level** property, not a
Lucky-Cat bug.

### The complement to HTTP/2: spend one connection well

HTTP/2 multiplexes every stream over a single TCP connection — the cap becomes
the server-tunable `SETTINGS_MAX_CONCURRENT_STREAMS` (~100). That is being
addressed separately in pounce (a version bump is in flight; see
`pounce-0-7-adoption.md`). This RFC is the **Chirp-level complement**: instead of
N persistent connections, open **one** and carry many named topics over it. The
primitive helps on **both** transports — it is strictly fewer connections on
HTTP/1.1, and fewer streams (less server bookkeeping, one reconnect/backoff
channel) on HTTP/2.

### The mental model: a live "global variable"

The author's framing: a `live()` topic is like a **static-site-generator global
variable**, but live. You declare a value once on the server, then bind it
**anywhere** in your templates — topbar, a modal, a sidebar — with
`{{ live('balance') }}`, and the framework keeps **every** binding in sync from
the single shared connection.

This is **strictly more than OOB**. An `hx-swap-oob` swap targets exactly **one**
element id. A **topic** fans out to **N** elements: htmx's `sse-swap="balance"`
uses `querySelectorAll`, so every element listening for the `balance` event swaps
when one `event: balance` arrives. The `balance` value can live in the topbar
*and* the deposit modal simultaneously — a cardinality OOB cannot express.

---

## 2. Goals / Non-Goals

### Goals

| Goal | Priority |
|------|----------|
| One shared SSE connection (`/live`) carrying many named topics | Must |
| A topic fans out to N bound DOM elements (declare-once, bind-many) | Must |
| `@app.live('topic')` server registry — thread-safe, register-before-freeze | Must |
| `{{ live('topic') }}` (scalar) + `{{ live_topic('topic') }}` (HTML fragment) helpers | Must |
| SSR initial value (no empty-then-fill flash) | Must |
| Additive — existing `sse_scope`, `EventStream`, OOB self-routing keep working | Must |
| `app.check()` dead-binding detection (bound `live('x')` with no producer; #238) | Must |
| `app.check()` WARN on >1 persistent SSE scope (the HTTP/1.1 footgun) | Must |
| Per-page topic subscription (`/live?topics=...`) | Should |
| Coexist with OOB/`Fragment` payloads on the same connection | Should |
| Free-threading (3.14t) safe registry + fan-out bus | Must |

### Non-Goals

- **Raising the HTTP/1.1 6-connection cap.** `live()` reduces N→1 per page; the
  cap is browser+protocol level. The real cap relief is HTTP/2 (pounce, in
  flight). If an app keeps separate `sse_scope` routes *alongside* `/live`, the
  footgun returns — hence the `app.check()` WARN.
- **A new wire format.** `live()` rides the existing `SSEEvent(event=...)` named
  channel and htmx 2 `sse-swap`. No new SSE framing.
- **A client store / offline cache / navigation persistence.** That was Option B
  of `rfc-shared-store.md` (Alpine store). Out of scope here; `live()` is push,
  not persistence.
- **Replacing OOB or reactive blocks.** `live()` is a third, additive layer
  alongside `register_oob_region` and `reactive_stream`.
- **Generic client-side compute.** A topic carries a server-rendered value; the
  client only swaps it into bound elements.

---

## 3. Background — what already exists (this is a thin layer)

Reviewers should see this is **transport reuse**, not a rewrite. Every substrate
the design needs is already in the tree.

| Layer | Symbol / file | What it already does |
|-------|---------------|----------------------|
| Named-event wire format | `SSEEvent(data, event, id, retry)` — `src/chirp/realtime/events.py:12-48` | `encode()` emits `event: <topic>\n` + one `data:` line per CRLF-normalized payload line + blank terminator (`events.py:28-40`). Exactly what htmx `sse-swap="<topic>"` matches on. `__post_init__` rejects CR/LF/NUL in `event`/`id` (`events.py:43-48`) — topic names are sanitized for free. |
| Stream container | `EventStream(generator, event_type, heartbeat_interval, allow_origin)` — `events.py:51-99` | Accepts `str`/`dict`/`Fragment`/`SSEEvent`. Same-origin by default (`allow_origin=None`). Heartbeat bound 1.0–300.0s. |
| Type dispatch | `_format_event()` — `src/chirp/realtime/sse.py:331-374` | `SSEEvent` → encode as-is; `Fragment` **with target** → `SSEEvent(event=target)` **with no OOB wrapper** (`sse.py:354-362`, comment explains why — an `hx-swap-oob` wrapper would replace the `sse-swap` element and break future updates); `Fragment` **without target** / `str` → the default `message` channel; `dict` → JSON. **Three transports already share one stream.** |
| Lifecycle | `handle_sse()` — `sse.py` | Heartbeat (`: heartbeat\n\n`), `close_event`, `sse_retry_ms`, disconnect monitor that races the producer (FIRST_COMPLETED) and awaits the generator's `aclose()` so `try/finally` cleanup runs, **per-event render-error isolation** (one bad block emits an `error` event without killing the stream). All inherited for free by a `/live` `EventStream`. |
| Client substrate | htmx 2 `hx-ext="sse"` + `sse-connect="/live"` + child `sse-swap="<topic>"` | One connect element, N descendant sinks. htmx `querySelectorAll` excludes the root, so swap sinks **must** be children. Proven in-repo: `examples/chirpui/rag_demo/templates/ask.html` (one connect, `sse-swap="sources"`/`"answer"`/`"share_link"`). |
| One connect macro | `sse_scope(url, swap, ...)` — `src/chirp/templating/macros/chirp/sse.html` | Emits `<div hx-ext="sse" sse-connect="{url}" hx-disinherit="hx-target hx-swap"><div sse-swap="{swap}" hx-target="this">`. The exact wrapper+sink shape a `live()` shell reuses. |
| Pub/sub fan-out | `ReactiveBus` — `src/chirp/pages/reactive/bus.py` | Scope-keyed, free-threaded: `threading.Lock` + per-subscriber `asyncio.Queue` + cross-thread `loop.call_soon_threadsafe` delivery + bounded `maxsize=256` back-pressure with throttled drop logging. Docstring (line 33): "Modeled on chirp's `ToolEventBus`." `ToolEventBus` (`src/chirp/tools/events.py`) is the simpler unscoped sibling. |
| Bus→stream adapter | `reactive_stream()` — `src/chirp/pages/reactive/stream.py:36-129` | `async for change in bus.subscribe(scope): yield Fragment(..., target=ref.target_id)`. The reference one-connection-many-block push engine. A `/live` merge generator generalizes this from one scope to many topics. |
| Contract crossref | `check_sse_event_crossref()` — `src/chirp/contracts/rules_sse.py:148-223` | Already cross-references template `sse-swap` values against `SSEContract.event_types` (declared) + AST-inferred `SSEEvent(event=)`/`Fragment(target=)` literals (emitted). Flags undeclared listeners + unlistened producers. |
| Declared events | `SSEContract(event_types: frozenset[str], fragments)` — `src/chirp/contracts/declarations.py:15-20` | The declared-events surface the crossref reads. The `live()` producer registry feeds this. |

**Conclusion:** level-1 multiplexing (merge N `sse_scope`s into one connection)
is achievable **today** with zero wire-format changes — OOB fragments self-route
and named-event topics ride their own `event:` field on the same stream. The new
work is the **ergonomic layer (level 2)**: the registry, the helpers, the
SSR-seeded sink, and the contract checks.

---

## 4. Design

### 4.1 Two levels

1. **Multiplex** — merge several `sse_scope` connections into one `/live`
   connection. Largely possible today; OOB fragments already self-route via
   `hx-swap-oob` in the HTML and ride the default `message` channel.
2. **Live-values / topics** — the new ergonomic layer: a server topic registry,
   a `{{ live('topic') }}` binding that fans one named event out to N elements,
   and SSR seeding. This RFC centers on (2), which *also* delivers (1)'s
   connection efficiency.

### 4.2 The single `/live` route + fan-in

One framework route (`/_chirp/live`, reserved prefix; or a configurable `/live`)
returns an `EventStream` whose generator **merges** all registered topic sources
into one named-event stream.

**The merge primitive is the bus's single-queue-per-subscriber design — not a
task group.** There is no generic fan-in primitive in `src/chirp/realtime/`
(only `events.py` + `sse.py`). The codebase's blessed concurrent-source merge is
`anyio.create_task_group()` (used in `templating/suspense.py` +
`templating/streaming.py`), but it is heavier than needed here: `ReactiveBus`
already collapses N producers into **one** async iterator per subscriber via a
single `asyncio.Queue`. Each producer calls `bus.emit(topic, value)`; the `/live`
generator subscribes to the requested topics and drains one queue.

```python
# Conceptual /live handler (framework-internal, auto-registered at freeze)
async def _live_stream(request: Request) -> EventStream:
    registry = request.app.live_topics            # frozen read accessor
    topics = registry.resolve(request.query.get("topics"))  # per-page subset

    async def generate():
        async for topic, html in registry.bus.subscribe_many(topics):
            # Fragment(target=topic) → SSEEvent(event=topic), NO OOB wrapper.
            # Equivalent: yield SSEEvent(data=html, event=topic)
            yield SSEEvent(data=html, event=topic)
        # bus.subscribe_many's finally unsubscribes every topic on disconnect

    return EventStream(generate())  # inherits heartbeat / close / aclose cleanup
```

Per-event error isolation in `handle_sse` (`sse.py:185-231`) is **load-bearing
here**: one topic's render failure must not kill the shared connection, or the
whole connection-budget win is undone. The merge generator must keep isolation
intact (render inside the per-event boundary, not eagerly in the generator).

### 4.3 The `@app.live('topic')` registry

Mirror `@app.live_block` exactly (`src/chirp/app/__init__.py:470-510`): a
`_check_not_frozen()` guard plus a decorator that stows a **frozen** spec into a
new `MutableAppState.live_topics` field (`src/chirp/app/state.py`, alongside
`live_blocks` at line 168 and `oob_registry` at line 152). The runtime fan-out is
backed by a `ReactiveBus` keyed by topic name.

```python
@dataclass(frozen=True, slots=True)
class LiveTopicSpec:
    """Declaration of one live topic (one producer, many bindings)."""
    name: str
    source: Callable[..., AsyncIterator[Any]] | None  # async generator of values
    initial: Callable[[], Any] | None = None          # SSR seed getter
    render: Callable[[Any], str] | None = None         # value → HTML (defaults to str)
    coalesce: bool = True                              # latest-wins (drop-safe)
```

```python
@app.live("balance", initial=wallet.balance)
async def balance_topic():
    """One PRODUCER for the 'balance' topic. Many bindings, one owner."""
    async for new_balance in wallet.watch():
        yield new_balance     # framework renders via spec.render and emits event: balance
```

**Free-threading (3.14t):** `LiveTopicSpec` is frozen+slots. The registry's
mutable maps (`{topic: spec}`, current-value cache, bound-element sets) are
guarded by a `threading.Lock` mirroring `OOBRegistry._contract_lock`
(`src/chirp/templating/oob_registry.py:52`). The fan-out bus is `ReactiveBus`
(already free-thread-safe via Lock + per-subscriber `asyncio.Queue` +
`call_soon_threadsafe`). Cross-thread emits (a topic source in `sync+thread`
mode) must use the bus's `call_soon_threadsafe` path — so `/live` requires
`worker_mode="async"` (Lucky Cat already sets this; document the requirement).

**One producer per topic, many bindings.** Two SSE sources `innerHTML`-swapping
one element fight and flicker (Lucky Cat's `app.py` documents this repeatedly —
`#lucky-cat-ticker` has a single owner). The registry enforces a single
producer per topic name; many `{{ live('x') }}` bindings are the point.

### 4.4 Template helpers — `live()` (scalar) + `live_topic()` (HTML fragment)

> **Naming.** `live_block`/`LiveBlockSpec` is **already** a different feature
> (freeze-time dynamic-block placeholders, `src/chirp/live_blocks.py`). The
> fragment helper here is named **`live_topic()`**, the spec is
> **`LiveTopicSpec`**, and the registry is **`LiveTopicRegistry`** to avoid
> shadowing. Final names are an Open Question (§11) pending steward sign-off.

Both helpers emit an `sse-swap` **sink element** (a *child* of the one shared
`sse-connect` wrapper — never the connect element, which `check_sse_self_swap`
ERRORs on). The sink is **SSR-seeded** with the current value so there is no
empty-then-fill flash (htmx's default `sse-swap` swap is `innerHTML`, which
replaces inner content on the first event).

```kida
{# scalar value — seeds inner text from spec.initial #}
{{ live('balance') }}
{# emits: <span sse-swap="balance" hx-target="this">1,234</span> #}

{# HTML fragment — seeds inner HTML from a rendered block #}
{{ live_topic('ticker') }}
{# emits: <div sse-swap="ticker" hx-target="this"><!-- rendered block --></div> #}
```

The single `sse-connect` wrapper is opened **once** in the shell (reusing the
`sse_scope` shape, with `hx-disinherit="hx-target hx-swap"` so live bindings in a
boosted shell don't inherit `#main`):

```kida
{# Shell layout — ONE connection for ALL topics on the page #}
<div hx-ext="sse" sse-connect="{{ live_connect() }}" hx-disinherit="hx-target hx-swap">
  {# ... entire page; every {{ live('x') }} sink lives somewhere in here ... #}
</div>
```

`live_connect()` is a request-aware global (the `get_request()`/ContextVar idiom
of `url_for`/`fragment_url`, `src/chirp/app/compiler.py:472-489`) that collects
the topics referenced on this render and emits `sse-connect="/live?topics=balance,ticker"`.
The SSR seed comes from `spec.initial()` (precedent: Lucky Cat's `meow_balance`
global = `wallet.balance()`, seeded into context by `pages/_context.py`).

### 4.5 Coexistence with OOB / `Fragment` / `EventStream`

`live()` topics are **additive transport (1)** on the same stream that already
carries:

| Transport | Mechanism | Cardinality |
|-----------|-----------|-------------|
| **Topic** (this RFC) | `SSEEvent(event=topic)` / `Fragment(target=topic)`, **no** OOB wrapper | 1 name → **N** elements (htmx `querySelectorAll`) |
| **OOB self-route** | `Fragment` with no target → default `message` channel, HTML bakes `hx-swap-oob` | 1 → **1** id (per OOB fragment) |
| **Framework meta** | `chirp:sse:meta` retry, `error`, configured `close_event` | n/a |

All three already multiplex through `_format_event` (`sse.py:345-374`)
**unchanged**. Existing `sse_scope` consumers and OOB self-routing fragments keep
working on the same connection — strictly additive.

### 4.6 When to use a topic vs an OOB twin

| Use a **topic** (`live('x')`) | Use an **OOB twin** (`register_oob_region` / `Fragment(hx-swap-oob)`) |
|---|---|
| One logical value shown in **many** places (balance in topbar AND modal) | One specific element id updated **atomically** |
| Idempotent, latest-wins value (price, count, status) | A specific region replaced as a unit |
| Bound by event name; element survives repeated swaps | Targeted by DOM id; element may be replaced |

Rule of thumb: **a value with multiple homes → topic; a single region atomic
swap → OOB.** Lucky Cat's `balance` (topbar + deposit modal) is the canonical
topic; a kanban card moving columns is OOB.

### 4.7 Coalescing-latest vs append (a real design decision, not a footgun)

`ReactiveBus` **drops** events under back-pressure (full subscriber queue,
`maxsize=256`, throttled WARN). For `balance` bound in the topbar *and* a modal,
a dropped update would desync the bindings.

**Decision: `live()` topics are coalescing-latest by default (`coalesce=True`).**
A live *value* is idempotent and last-write-wins, so dropping a stale update is
safe — the next emit reconciles every binding. `coalesce=True` lets the registry
collapse a queued-but-undelivered value with the newest one (latest-wins),
making drops harmless. Append-style topics (a log tail, a chat stream where every
line matters) set `coalesce=False` and are documented as drop-sensitive; the
producer must keep its queue drained or accept lossy delivery. This is surfaced
in the spec, not papered over.

---

## 5. API Reference

### Server: `@app.live(name, *, initial=None, render=None, coalesce=True)`

```python
from chirp import App, Fragment

app = App(config)
wallet = Wallet()

# Scalar topic: balance shown in topbar AND deposit modal.
@app.live("balance", initial=wallet.balance)
async def balance_topic():
    async for amount in wallet.watch():
        yield f"{amount:,}"        # rendered to event: balance

# HTML-fragment topic: a rendered block.
@app.live(
    "ticker",
    initial=lambda: market.spotlight(),
    render=lambda spot: render_block("market/ticker.html", "ticker_strip", spot=spot),
)
async def ticker_topic():
    async for spot in market.spotlight_stream():
        yield spot
```

- Registration is **setup-only** (`_check_not_frozen()`); the `/live` route is
  appended during `_freeze` **before** `_compile_routes`
  (`src/chirp/app/compiler.py:423-428`), exactly like
  `make_fragment_dispatch_pending_route`.
- The `/live` route auto-registers **only when topics exist** (mirror the
  `if self._mutable.live_blocks` gating), so apps with no topics pay nothing.

### Template: `live()`, `live_topic()`, `live_connect()`

```kida
{# Shell layout (once) #}
<div hx-ext="sse" sse-connect="{{ live_connect() }}" hx-disinherit="hx-target hx-swap">

  {# Topbar #}
  <span class="balance">{{ live('balance') }}</span>

  {# ... later, in the deposit modal, the SAME topic, a SECOND binding #}
  <div class="modal__balance">{{ live('balance') }}</div>

  {# HTML-fragment topic #}
  {{ live_topic('ticker') }}
</div>
```

- These globals are registered **only when `live_topics` is non-empty** (mirror
  `alpine_json_config`'s conditional registration), and the shell must guarantee
  the **htmx-ext-sse** extension is loaded (see §7 — it is *not* injected by
  `htmx_snippet`).

### Wire (what hits the socket)

```
event: balance
data: 1,234

event: ticker
data: <div class="ticker-strip">...</div>

: heartbeat

event: balance
data: 1,250
```

Every `<... sse-swap="balance">` element on the page `innerHTML`-swaps on each
`event: balance` — topbar and modal update together from one connection.

---

## 6. `app.check()` Integration

### 6.1 Dead-binding detection (chirp issue #238 — the dead-ticker class)

A bound `{{ live('x') }}` / `sse-swap="x"` with **no registered producer** is a
silent dead binding — the element never updates. This is exactly the dead-ticker
class filed as #238.

**Why AST inference is insufficient.** `_infer_emitted_events`
(`rules_sse.py:51-83`) only sees **literal** string kwargs and returns `None`
(→ INFO, not ERROR) for dynamic event names. `live('topic')` producers are
dynamic by nature, so dead-binding detection **must** use the **explicit
producer registry**, not AST inference — otherwise it degrades to INFO and
defeats the #238 goal.

New rule `check_live_topics` (new `src/chirp/contracts/rules_live_topics.py`),
wired into `checker.py` adjacent to `check_live_blocks` (`checker.py:854-855`)
and the SSE checks (`checker.py:519-522`), reading a new **`live_topics` field on
`ContractCheckSnapshot`** (`src/chirp/app/state.py:196+`, mirroring the
`oob_registry` snapshot field) — never reaching into half-built mutable state:

- **Dead binding (ERROR):** every `sse-swap="x"` emitted by `live('x')` /
  `live_topic('x')` with no registered `@app.live('x')` producer.
- **Orphan producer (INFO/WARNING):** a registered topic no binding listens for.
- Reuses the existing `extract_sse_swap_values()` + `SSE_CONNECT_TAG` scanner
  (`rules_sse.py:25-27`, `patterns.py:46`) — `live('x')` emits `sse-swap="x"`, so
  the same scanner already sees the listeners.

**Merged-topic resolution.** `check_sse_event_crossref` matches `sse-swap`
listeners to the route of the *enclosing* `sse-connect` (`rules_sse.py:170-181`).
With one `/live` carrying many topics, **all** topic listeners resolve to
`/live`, so `/live`'s producer set must declare **every** topic or every binding
flags. `check_live_topics` understands the merged model: it validates against the
**registry**, not the per-route inferred set. The registered topic names should
also be fed into `SSEContract.event_types` for `/live` so the existing crossref
stays consistent.

### 6.2 HTTP/1.1 footgun WARN — >1 persistent SSE scope

New rule (or extension of `check_sse_connect_scope`): **WARN** when an app opens
more than one **persistent** `sse-connect` per shell/layout. Substrate exists —
`_SSE_CONNECT_TAG_PATTERN` (`src/chirp/contracts/patterns.py:47`) already
enumerates every `sse-connect` URL per template. The net-new analysis is
distinguishing **layout/shell-level** (persistent, every-page) scopes from
per-page transient ones — the checker does not model persistent-vs-transient
today, so this rule must cross-reference `sse-connect` locations against
layout/shell templates (the layout-chain data exists but is not yet joined with
SSE-connect locations).

### 6.3 Category wiring

New categories (e.g. `live_topic_dead_binding`, `live_topic_orphan`,
`sse_persistent_scope`) register in the terminal-report category map
(`src/chirp/server/terminal_checks.py:170-229`) under the existing
**"OOB / Suspense / SSE"** section.

---

## 7. Client / Transport

### 7.1 htmx `sse-swap` wiring

- **One** `hx-ext="sse" sse-connect="/live"` element in the shell; **N** child
  `sse-swap="<topic>"` sinks (htmx `querySelectorAll` excludes the root, so sinks
  **must** be descendants — `check_sse_self_swap` ERRORs the violation).
- `hx-disinherit="hx-target hx-swap"` on the connect element + `hx-target="this"`
  on each sink, or boosted-shell bindings inherit `#main` and swap the whole page
  (`check_sse_connect_scope` ERRORs this).
- **The htmx-ext-sse extension is NOT vendored and NOT injected by
  `htmx_snippet`** (`src/chirp/server/htmx.py`) — it is loaded only by three
  hardcoded literal tags (`shell.html`, `boost.html`, `cli/templates/v2.py`) from
  `unpkg.com/htmx-ext-sse@2.2.2/sse.js`. A `live()` shell must guarantee the ext
  is present (extend `htmx_snippet`/inject, or require the shell layout) or every
  binding silently does nothing. This is a hard prerequisite, not a nicety.

### 7.2 Reconnection / backoff — one channel, one backoff

With N separate `sse_scope`s, the browser runs N independent reconnect/backoff
loops; a flaky network produces N reconnection storms. One `/live` connection =
**one** reconnect channel and **one** backoff. The framework already emits a
leading `chirp:sse:meta` retry event from `sse_retry_ms` (`sse.py:88-98`) — set
it once on the `/live` `EventStream` and the browser honors a single retry policy
for all topics.

> **Heartbeat sentinel gotcha.** `heartbeat_interval==15.0` is a sentinel:
> `handler.py:420-421` only overrides it with the app-level
> `sse_heartbeat_interval` when it is **exactly** 15.0. A `/live` `EventStream`
> constructed with an explicit non-15.0 interval will **not** pick up the global.
> Construct `/live` with the default and let the global override apply, or
> document the exception.

### 7.3 HTTP/2 synergy

The cap relief is HTTP/2 multiplexing (`SETTINGS_MAX_CONCURRENT_STREAMS` ~100),
in flight in pounce (`pounce-0-7-adoption.md`). `live()` is the **complement**,
not a substitute:

- **On HTTP/1.1:** strictly fewer held connections (N→1), directly relieving the
  6-cap exhaustion that blocks boosted navigation.
- **On HTTP/2:** fewer concurrent streams + one reconnect/backoff channel + less
  server-side per-stream bookkeeping. Still a win.

Each `/live` connection still holds **one** HTTP/1.1 connection — `live()` does
not remove the cap (Non-Goal). Mixing `/live` with leftover `sse_scope` routes
re-introduces the footgun, which §6.2 flags.

---

## 8. Security

- **Same-origin by default.** `EventStream.allow_origin=None` emits no
  `Access-Control-Allow-Origin` (`events.py:74-82`, `sse.py:72-76`). A
  cross-origin `/live` needs an explicit `allow_origin`; **`CORSMiddleware` does
  not apply to the SSE byte stream** (`sse.py:60-65`) — the value must be set on
  the `EventStream`.
- **GET-only, no CSRF.** `/live` is a read-only GET SSE endpoint (no mutation),
  so it is outside the CSRF surface — consistent with existing `EventStream`
  routes marked `referenced=True`.
- **Topic-name validation.** `SSEEvent.__post_init__` rejects CR/LF/NUL in
  `event` (`events.py:43-48`). The `live('x')` key charset must be documented and
  validated at registration time (recommend `[A-Za-z0-9_.:-]+` to match the
  `sse-swap` attribute + existing reactive scope keys); reject at
  `@app.live(...)` registration, not at emit.
- **Audience / presence.** `ReactiveBus` already supports `audience` filtering
  and `ConnectionInfo` presence; per-user topics (e.g. a private `balance`)
  should ride the bus's audience filter rather than a custom path.

---

## 9. Backwards-Compatibility & Migration

**Strictly additive.** Nothing existing changes behavior:

- `sse_scope(url)` macro, `EventStream`, `Fragment(target=...)` /
  `hx-swap-oob` self-routing, `register_oob_region`, `reactive_stream` — all keep
  working unchanged.
- `_format_event` dispatch is untouched (`live()` emits the same
  `SSEEvent(event=topic)` it already handles).
- The `/live` route and `live*` globals only exist when topics are registered.

**Coexistence story.** An app can adopt `live()` incrementally — migrate the two
persistent shell scopes first (the connections that block navigation), leave
per-page transient scopes until later. `app.check()` (§6.2) nudges toward
collapsing remaining persistent scopes but does not force it. There is no
deprecation of `sse_scope`; it remains the right tool for a single transient
per-page stream.

**Public-API gate.** Any top-level `chirp` export (`src/chirp/__init__.py` lazy
map + `_STABILITY` + `__all__`) is snapshot-tested
(`tests/test_public_api_docs.py`, `docs/public-api.md`) — a **stop-and-ask**
surface. `@app.live`, the template globals, the `/live` route, and the new check
categories are likewise stop-and-ask surfaces per root `AGENTS.md`. This RFC
proposes the shape; sign-off precedes export.

---

## 10. Reference Migration — Lucky Cat

Lucky Cat is the showcase: it holds the exact connection-exhaustion this
primitive solves, and `balance` is the canonical multi-binding topic (topbar +
deposit modal).

### Before — N persistent connections

`examples/chirpui/lucky_cat/pages/_layout.html` opens **two** always-on SSE
connections on every page:

```kida
{{ sse_scope("/notifications/stream", wrapper_class="luckycat-notif-sse") }}
{{ sse_scope("/ticker/stream", wrapper_class="luckycat-ticker-sse") }}
```

Plus per-page streams (`/markets/{symbol}/stream`, `/ft/stream`). `balance` is
duplicated by hand: `meow_balance_swap` bakes `#lucky-cat-balance` + `hx-swap-oob`
in the topbar, and the deposit-modal balance is a separate OOB target — two
hand-maintained sites for one value.

| Page | Persistent shell SSE | Per-page SSE | Total held |
|------|----------------------|--------------|-----------|
| Home | notifications + ticker | — | **2** |
| Market detail | notifications + ticker | `/markets/{sym}/stream` | **3** |
| Trade tape open | notifications + ticker | `/markets/{sym}/stream` + `/ft/stream` | **4** |

At 4 held + the page's own boosted-nav budget → the 6-cap wall; `GET /health`
times out.

### After — ONE `/live` connection, topics

```python
# app.py — three producers, one connection
@app.live("notifications", initial=lambda: notif_store.unread())
async def notifications_topic(): ...

@app.live("ticker", initial=lambda: market.spotlight(),
          render=lambda s: render_block("market/ticker.html", "ticker_strip", spot=s))
async def ticker_topic(): ...

@app.live("balance", initial=wallet.balance)
async def balance_topic(): ...
```

```kida
{# _layout.html — ONE connection #}
<div hx-ext="sse" sse-connect="{{ live_connect() }}" hx-disinherit="hx-target hx-swap">
  <span id="notif-badge">{{ live('notifications') }}</span>
  {{ live_topic('ticker') }}
  <span class="luckycat-token">{{ live('balance') }}</span>   {# topbar #}
  ...
  <div class="deposit-modal__balance">{{ live('balance') }}</div>  {# SAME topic, 2nd binding #}
</div>
```

| Page | Persistent shell SSE | Per-page SSE | Total held |
|------|----------------------|--------------|-----------|
| Home | **/live** (notifications + ticker + balance) | — | **1** |
| Market detail | **/live** | per-page market topic on `/live?topics=...` | **1** |
| Trade tape open | **/live** | trade-tape topic on `/live?topics=...` | **1** |

`balance` now has **two bindings, one producer, zero hand-maintained OOB twins** —
the topbar and modal stay in sync automatically. Connection count drops from up
to 4 to **1**; boosted navigation always has free sockets.

> Per-page streams (market detail, trade tape) fold into `/live` via
> `?topics=...` once their producers are registered, or remain transient
> `sse_scope`s during phased migration (only the >1 *persistent* check fires).

---

## 11. Phased Rollout & Open Questions

### Phased rollout

| Phase | Deliverable | Proof |
|-------|-------------|-------|
| **MVP** | `LiveTopicSpec` + `LiveTopicRegistry` (frozen + Lock) + `@app.live` + `/live` route (auto-registered, `ReactiveBus`-backed merge) + `live()`/`live_topic()`/`live_connect()` globals + htmx-ext-sse guarantee | Unit + free-threading concurrency test (Lock proof, root `AGENTS.md` requirement); a 2-binding topic test (topbar + modal both swap from one event); SSE multiplex integration test |
| **Contract** | `check_live_topics` dead-binding (ERROR, #238) + orphan-producer + >1-persistent-scope WARN; new categories in terminal report; `ContractCheckSnapshot.live_topics` field | A `@pytest.mark.issue(238)` test (dead binding → ERROR); a >1-persistent-scope WARN test; snapshot-test updates for any public export |
| **Migration** | Lucky Cat collapses notifications + ticker + `balance` onto one `/live`; before/after connection-count assertion; browser smoke (verify in a real browser + link-crawl — TestClient string-asserts give false green) | `GET /health` returns fast while `/live` is held; balance binding syncs in topbar AND modal in a real browser; `app.check()` clean |

### Open questions

1. **Naming (blocker).** `live_block`/`LiveBlockSpec`/`MutableAppState.live_blocks`
   already exist for an unrelated feature. Proposed: `live()` /
   `live_topic()` / `LiveTopicSpec` / `LiveTopicRegistry` /
   `MutableAppState.live_topics`. Is `live_topic()` distinct enough from
   `live_block` for readers, or should the fragment helper be e.g.
   `live_html()` / `live_region()`? Needs steward sign-off.
2. **Route path.** `/_chirp/live` (reserved framework prefix, collision-detected
   via `InternalRouteSpec`, `debug_runtime.py:153-161`) vs a friendlier `/live`
   (user-visible, possible app collision)? Reserved prefix is safer; confirm.
3. **Per-page subscription transport.** `/live?topics=a,b` query (handler reads
   `request.query`) vs path-segment vs a per-page connect element. Query is the
   lightest; does it interact badly with htmx reconnection (URL must be stable
   across reconnects)?
4. **Coalesce default.** `coalesce=True` (latest-wins, drop-safe) proposed as
   default (§4.7). Confirm append-style topics (`coalesce=False`) are a real need
   for the MVP or defer them.
5. **Render location.** Should `render`/`initial` run on the request thread (SSR
   seed) and the topic source's loop (live emits)? Confirm error isolation holds
   when render runs inside `handle_sse`'s per-event boundary vs eagerly in the
   merge generator.
6. **Public export surface.** Does `@app.live` warrant any top-level `chirp`
   export, or is it method-only + template-global-only (no `__init__.py` change)?
   Method-only minimizes the stop-and-ask surface.
7. **Config flag.** Is a new `AppConfig` field needed (e.g. `live=True` to gate
   the ext + route), or is "auto-on when topics registered" sufficient? A new
   `AppConfig` field is itself a stop-and-ask surface.

---

## 12. Multi-Worker Backplane & the Pure-Derived Contract

> ## ⚠ STATUS: NOT-NOW DESIGN — NOTHING IN §12 IS SHIPPED
>
> **This section is a planning artifact, not documentation for existing
> behavior.** No `SignalBus` protocol, no adapter-selection seam, no
> `RedisSignalBus`, and no `signal_bus` / durable-mode config exist in the tree
> today. Do **not** cite §12 as a feature; do **not** scaffold against it.
>
> | | |
> |---|---|
> | **Section status** | Drafted design — **not implemented**, not scheduled |
> | **Folder** | `plan/drafted/` (stays here until accepted; do **not** move to `plan/completed/`) |
> | **Shipped today** | Only the **single-node** `signal()` primitive (§1–11 + §12.1's "shipped" rows). The backplane below is the opt-in upgrade. |
> | **Gate** | Realtime **+** app/state **+** contracts steward sign-off, plus public-API & changelog collateral, **before any backplane code lands** (see §12.7) |
>
> **Status carry-over.** Section 1–11 describe the single-node `signal()`
> primitive. That primitive **shipped** in the build session that produced this
> RFC: `@app.signal` / `@app.derived` / `app.emit` + the `signal()` /
> `signal_block()` / `signal_connect()` template globals
> (`src/chirp/realtime/signals.py`, `signal_globals.py`, `signal_stream.py`,
> `contracts/rules_signals.py`), with Lucky Cat migrated onto one
> `/_chirp/live` connection. **Everything from §12.2 onward is not implemented** —
> it is the opt-in production upgrade. It graduates the *transport* from
> process-local to a pluggable backplane and formalizes the contract that makes a
> `derived` correct on any worker.

### 12.1 The problem — the bus is per-worker, so realtime is single-process

The shipped fan-out is `SignalRegistry.bus: ReactiveBus`
(`src/chirp/realtime/signals.py:144`) — an **in-process**, scope-keyed
`threading.Lock` + per-subscriber `asyncio.Queue` bus
(`src/chirp/pages/reactive/bus.py:25`). Every emit
(`SignalRegistry.emit` → `_publish` → `bus.emit_sync`,
`signals.py:247-328`) and every derived cascade (`_cascade`, `signals.py:271`)
delivers **only to subscribers living in the same OS process**.

That is correct for one worker and broken for many — and the breakage is **not
just a scale ceiling, it is a multi-user correctness bug on a single machine**:

- An `app.emit("balance", ...)` on worker A reaches only the `/_chirp/live`
  subscribers pinned to worker A. A user whose long-lived SSE connection landed
  on worker B never sees the event. **User A's action cannot update user B's
  screen** — the defining promise of server-pushed realtime — the moment a
  second worker exists.
- A `@app.signal(source=...)` async generator is pumped by a background task
  *inside one worker's event loop* (`signal_stream.py:64-84`). Its yields fan
  out on that worker's bus only.

**Deterministic evidence (this session).** Lucky Cat was forced to `workers=1`
(`examples/chirpui/lucky_cat/app.py:96`) precisely because of this. The comment
records the reproduction: running multiple OS-process workers split *all* the
in-memory state (wallet, trade store, notifications log, SimFeed) **and** the
signal bus across processes, and the `/_chirp/live` connection — pinned to one
worker — stalled page loads that landed on a tied-up worker (the observed
"white screen" / freeze). An 11-worker run froze; one worker is the only
configuration in which the in-memory example is coherent. The freeze and the
split are two faces of the same fact: **the bus and the source of truth are
process-local**.

### 12.2 The design — a pluggable `SignalBus` protocol

Introduce a transport seam. Today's `ReactiveBus` becomes the **default
in-process implementation** (dev / single-node / the in-memory example);
production swaps in a network-backed adapter **without touching a line of
`signal()` app code**. The `@app.signal` / `@app.derived` / `app.emit` surface,
the template globals, and `/_chirp/live` are unchanged — only the bus behind
`SignalRegistry.bus` changes.

```python
from typing import Protocol, runtime_checkable
from collections.abc import AsyncIterator

@runtime_checkable
class SignalBus(Protocol):
    """Transport seam for signal fan-out. The in-process default is ReactiveBus;
    a network adapter (Redis / Postgres / NATS) makes emits cross-worker."""

    def publish(self, topic: str, payload: str) -> None:
        """Fan a rendered value out to every subscriber of *topic*, on any worker.

        Coalescing-latest / at-most-once: a dropped message under back-pressure
        is reconciled by the next publish (live values are idempotent). Safe to
        call from any thread (cross-thread/-worker delivery is the adapter's job).
        """

    def subscribe(self, topics: frozenset[str]) -> AsyncIterator[tuple[str, str]]:
        """Async-iterate ``(topic, payload)`` for every *topics* publish, until the
        consumer disconnects (the ``finally`` unsubscribes / closes the channel)."""
```

The two methods map exactly onto what `signal_stream.py` already does: the merge
generator subscribes to the page's topics and yields `SSEEvent(event=topic,
data=payload)` per delivery (`signal_stream.py:53-92`); each emit publishes a
rendered payload (`signals.py:316-328`). The `ReactiveBus` adapter wraps the
existing `subscribe(scope)` / `emit_sync` (one `topic` ↔ one `_SCOPE_PREFIX`
scope), so the default path is a no-op rename of today's behavior.

**Where the seam plugs in (concrete, as-built).** The single integration point is
`SignalRegistry.bus` (`signals.py:144`, today `field(default_factory=ReactiveBus)`).
Three call sites move behind the protocol; nothing else changes:

| As-built call site | Today | Behind the seam |
|---|---|---|
| `SignalRegistry._publish` (`signals.py:316-328`) | `self.bus.emit_sync(ChangeEvent(scope, …))` with the rendered payload recovered later from the cache | `self.bus.publish(name, rendered)` — render **eagerly** and put the payload on the wire, because a remote worker has no access to this worker's `_values` cache (see Risk R3) |
| `signal_stream._drain_scope` (`signal_stream.py:59-62`) | `async for _change in registry.bus.subscribe(_SCOPE_PREFIX + name)` then read the local cache | `async for topic, payload in registry.bus.subscribe(frozenset(names))` — payload arrives **in-band**, no cache read |
| `SignalRegistry.bus` default | `ReactiveBus()` | adapter chosen by the config seam (§12.2.1); default is the `ReactiveBus`-backed `InProcessSignalBus` |

The current design recovers the payload from the value cache on drain
(`signal_stream.py:87-92`) specifically to keep render off the stream hot path.
That optimization is **process-local by construction** — it cannot survive a
network hop. The backplane therefore inverts it: render at `publish` time and
carry the rendered string in-band. This is the single behavioral change inside the
shipped single-node path the backplane forces, and it is contained entirely in the
default `InProcessSignalBus` adapter; the `@app.signal` surface is untouched.

```python
class InProcessSignalBus:
    """Default adapter — wraps the shipped ReactiveBus. Dev / single-node / the
    in-memory example. Behaviorally identical to today; the only difference is
    the rendered payload travels in-band rather than via the value cache."""

    def __init__(self, *, maxsize: int = 256) -> None:
        self._bus = ReactiveBus(maxsize=maxsize)

    def publish(self, topic: str, payload: str) -> None:
        # ChangeEvent carries the rendered payload in changed_paths (same trick
        # as signals.py today), but now it IS the payload, not a marker.
        self._bus.emit_sync(ChangeEvent(scope=_SCOPE_PREFIX + topic,
                                        changed_paths=frozenset({payload})))

    async def subscribe(self, topics):
        # One ReactiveBus subscription per topic, fanned into one iterator —
        # exactly signal_stream._drain_scope's loop, lifted into the adapter.
        ...
```

### 12.2.1 Adapter-selection seam — `AppConfig` + a typed setter

Selection follows the **established `cache_backend` precedent** (`config.py:322`,
a string selector resolved to an adapter at startup) rather than inventing a new
mechanism. Two layers, mirroring how cache + sessions already work:

```python
# AppConfig (frozen, slotted) — new field, env-parity, stop-and-ask surface.
signal_bus: str = "memory"   # "memory" | "redis" | "nats" | "postgres"
# redis_url already exists (config.py:336) and is reused; nats/postgres add
# *_url fields only if/when their adapters land (deferred — keep the field set
# minimal for the first backplane).
```

- `"memory"` (default) → `InProcessSignalBus` — **identical to today**, zero new
  deps, the only config that keeps the in-memory example coherent.
- `"redis"` → `RedisSignalBus(config.redis_url)` — requires `chirp[redis]` (the
  extra **already exists**, `pyproject.toml`; reused, not added — see §12.2.2).
- Unknown value → startup `ValueError` naming the legal set (fail-loud, no
  silent fallback to in-process, which would re-introduce the multi-user
  correctness bug §12.1 describes).

For apps that need a custom adapter (a bespoke broker, an outbox table), a typed
setter escape hatch mirrors `app.set_cache_backend(...)` style:

```python
app.set_signal_bus(MyCustomBus())   # setup-only; _check_not_frozen guard
```

The setter is **setup-only** (raises `RuntimeError` after freeze, like every
other registry mutation) and overrides the `signal_bus` string. The string field
covers the 95% case from config/env; the setter covers the bespoke 5% without a
new `AppConfig` field per broker.

### 12.2.2 Optional-extra shape — reuse `redis`, do **not** add a `signals` extra

`chirp[redis]` (`redis>=5.0.0`) **already exists** and already backs
sessions + rate-limiting + the cache backend (`config.py`,
`middleware/sessions.py`, `cache/backends/redis.py`). `RedisSignalBus` reuses it —
**no new extra for Redis.** This matches the Optional-Dependencies cross-cutting
concern: the extra exists, missing-extra import errors must stay actionable
(`pip install chirp[redis]`), and core imports must not pull `redis`.

- **Redis:** `chirp[redis]` (existing). `RedisSignalBus` imports `redis` /
  `redis.asyncio` lazily inside the adapter (the `cache/backends/redis.py`
  pattern — import inside `connect()`, never at module top), so
  `from chirp import App` never imports `redis`.
- **NATS** (deferred): would need a **new** `chirp[nats]` extra
  (`nats-py>=2.x`). Out of scope for the first backplane; named here as a
  same-protocol alternative, not a deliverable.
- **Postgres `LISTEN`/`NOTIFY`** (deferred): reuses `chirp[data-pg]` (`asyncpg`,
  existing) — no new extra. Payload-size-limited, so it carries a *notification*
  and the consumer reads the rendered value from a shared cache (§12.4). Named as
  an alternative, not a first-backplane deliverable.

First-backplane deliverable is therefore **`memory` (default) + `redis` (reusing
the existing extra)**. NATS and Postgres are documented seams, deferred.

**Reference adapter — Redis pub/sub.** `publish` is one `PUBLISH signal:<topic>
<payload>`; `subscribe` runs a single `PSUBSCRIBE signal:*` (or `SUBSCRIBE` of
the requested topics) and feeds each message into the per-connection async
iterator. Reconnection is the adapter's responsibility and must be **transparent
to the SSE consumer**: on a dropped Redis connection, reconnect with bounded
exponential backoff and re-issue the subscription; because live values are
coalescing-latest (§4.7), a gap during reconnect self-heals on the next publish
— no replay needed for the live-value mode.

```python
class RedisSignalBus:
    def __init__(self, url: str, *, prefix: str = "signal:") -> None:
        self._redis = redis.from_url(url)        # publish side (sync-safe)
        self._prefix, self._url = prefix, url

    def publish(self, topic: str, payload: str) -> None:
        self._redis.publish(self._prefix + topic, payload)   # cross-worker fan-out

    async def subscribe(self, topics):
        backoff = 0.25
        while True:                              # transparent reconnect loop
            try:
                pubsub = redis.asyncio.from_url(self._url).pubsub()
                await pubsub.subscribe(*(self._prefix + t for t in topics))
                backoff = 0.25                   # reset after a clean connect
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        chan = msg["channel"].decode()
                        yield chan.removeprefix(self._prefix), msg["data"].decode()
            except asyncio.CancelledError:
                raise                            # consumer disconnected — stop
            except Exception:
                await asyncio.sleep(backoff)     # coalescing-latest self-heals the gap
                backoff = min(backoff * 2, 5.0)
```

**Alternatives, same protocol.** Postgres `LISTEN`/`NOTIFY` (zero extra
infra if the app already has Postgres; payload-size-limited, so it best carries
a *notification* and the consumer reads the rendered value from a cache),
and **NATS** (subject-based fan-out, built for exactly this) are equally valid
`SignalBus` adapters. The protocol is the contract; the wire is a choice.

**Where this sits in the landscape.** This is Chirp's analogue of **Phoenix
PubSub** (Elixir; the adapter seam under `Phoenix.Channel` broadcast — local PG2
by default, Redis adapter for clustering), **Rails ActionCable** (the
`subscription_adapter` config: `async` for dev, `redis` for production), and
**Django Channels** (the `CHANNEL_LAYERS` backend — in-memory for dev, Redis
channel layer for production). All three ship a single-node default and a
pluggable production backplane behind one broadcast API. `SignalBus` follows the
same proven shape, expressed in Chirp's hypermedia idiom: the payload on the
wire is **server-rendered HTML/text bound to an `sse-swap` topic**, not a JSON
event a client framework must interpret.

### 12.3 The pure-derived contract (formalized)

> **A `@app.derived` MUST be a pure function of its input signal VALUES. It must
> never read external or process-local mutable state.**

A derived's `compute(*dep_values)` receives the current cached values of its
`on=(...)` dependencies and returns the derived value (`signals.py:101-126`,
`_cascade` at `signals.py:271-314`). Restricting it to those inputs is what makes
a derived **deterministic on any worker**: the cascade recomputes from the same
cached dep values on every worker, so the badge a worker emits always agrees with
the value it derived from — no second, racing read of process-local state.

**The notif_badge fix (this session) is the canonical violation and repair.**
The badge derived originally computed `notifications.unread_count()` — a
process-local store read — instead of reading its input value. That is
non-deterministic across workers (each worker holds a separate store) and races
the read-watermark across threads (the source-pump thread vs. the route thread),
so the emitted badge could disagree with the list it shipped. This is the same
anti-pattern that earlier forced a `net_worth` derived to be dropped.

The fix carried the derived's input *in the signal value*: the `notifications`
signal now emits a frozen `NotifFeed(notes, unread)` whose `snapshot()` captures
the rows **and** the unread count atomically under one lock
(`examples/chirpui/lucky_cat/notifications.py:58-131`); `notif_badge` /
`notif_announce` compute purely from `feed.unread`
(`examples/chirpui/lucky_cat/app.py:340-360`). The pattern generalizes: **if a
derived needs a fact, the source signal's value must carry that fact** — a small
payload or a frozen dataclass — so the derived reads it from the input, never
from the world. (Companion framework fix: `_cascade` was made transitively
correct so a derived-of-a-derived also recomputes + re-emits on a single source
change; `signals.py:271`.)

### 12.4 State — the backplane carries the notification, not the source of truth

The backplane is a **fan-out transport for change notifications + rendered
values**, not a data store. It answers *"topic X just became this rendered
value — push it to every subscriber on every worker."* It is **not** where the
balance, the order book, or the notifications log live.

In a real production app this is already solved: the source of truth is a shared
database (or Redis as a store), so every worker reads the same balance and
renders the same value. Only the **bus** needs a backplane — to wake the SSE
connections on *other* workers when one worker mutates the shared store. The
in-memory Lucky Cat example is the **exception, not the template**: it keeps the
source of truth in process memory, which is *why* it must stay `workers=1`
(§12.1). A DB-backed app does not have the example's `workers=1` constraint once
the bus is backed; sharing state is the app's existing job, sharing the *signal*
is what `SignalBus` adds.

This also keeps the pure-derived contract honest: a derived reads its inputs from
signal values (replicated by the bus), and a primary signal's `initial` /
`source` read the shared store. No worker derives from its own private copy.

**Contract implication (new `app.check()` rule).** The multi-worker footgun is
*configuring `workers>1` (or the CPU-count default) with `signal_bus="memory"`* —
exactly the Lucky Cat reproduction (§12.1). This is statically detectable at
startup and must WARN (production: ERROR), extending `rules_signals.py` (which
already owns `signal_dead_binding` / `signal_orphan`, `rules_signals.py:100-117`):

- **`signal_bus_single_worker` (WARN, ERROR in production):** any signal
  registered **and** (`config.workers != 1`) **and** `signal_bus == "memory"` →
  "in-memory signal bus with multiple workers splits realtime across processes;
  set `signal_bus='redis'` (and a shared state store) or pin `workers=1`." The
  message names the exact fix, mirroring the secure-by-default `security_stack`
  env-aware severity policy. This rule is the contract that turns the Lucky Cat
  code comment into an enforced invariant.

The check reads a new **`signal_bus` field on `ContractCheckSnapshot`** (a string,
mirroring how `oob_registry` / `live_topics` snapshot fields are surfaced) — never
reaching into half-built mutable state.

### 12.5 Delivery semantics

Two modes, matching §4.7's `coalesce`:

| Mode | Semantics | Use for | Backplane requirement |
|---|---|---|---|
| **Live value** (`coalesce=True`, default) | **Coalesce-latest / at-most-once** — drop-safe; a dropped or reconnect-gapped message is reconciled by the next publish because the value is idempotent and last-write-wins | balance, price, count, status, the `notif_badge` derived | Plain pub/sub (Redis `PUBLISH`, Postgres `NOTIFY`, NATS core). No persistence; reconnect self-heals. |
| **Append stream** (`coalesce=False`) | **Durable / at-least-once** — every message matters (a log tail, a chat line); drops are data loss | event logs, chat history, audit tails | A durable channel (Redis Streams with consumer groups, NATS JetStream, an outbox table) + a replay/resume cursor across reconnects. |

The shipped single-node path is already coalescing-latest: the merge generator
reads the *latest cached* value on drain (`signal_stream.py:87-92`), so a bus
drop under back-pressure is reconciled by the next read. The backplane preserves
this for the live-value mode for free; the durable mode is a **later, opt-in**
addition (an adapter capability + a resume cursor), not part of the first
backplane.

### 12.6 Phasing — designed-in, not required

| Phase | Deliverable | Status |
|---|---|---|
| **Now (shipped)** | `signal()` / `derived()` / `emit` + globals + `/_chirp/live` + `rules_signals` contract, in-process `ReactiveBus`, Lucky Cat on one connection, pure-derived contract enforced by the `NotifFeed` refactor + transitive `_cascade` | **Done** (single-node) |
| **Backplane (opt-in, first deliverable)** | `SignalBus` Protocol (§12.2); `InProcessSignalBus` default (reframes today's `ReactiveBus` + the render-on-publish inversion); reference `RedisSignalBus` (reusing `chirp[redis]`); `signal_bus` `AppConfig` field + `set_signal_bus` setter (§12.2.1); `signal_bus_single_worker` contract rule (§12.4) | **Not implemented** |
| **NATS / Postgres adapters (later)** | Same `SignalBus` Protocol, different wire; NATS needs a new `chirp[nats]` extra, Postgres reuses `chirp[data-pg]` (§12.2.2) | **Not implemented** (deferred) |
| **Durable mode (later)** | `coalesce=False` append streams over a durable adapter (Redis Streams / JetStream) + reconnect resume cursor (§12.5) | **Not implemented** (deferred) |

The sequencing is deliberate: **`signal()` is useful single-node today** (one
connection, declare-once-bind-many, derived cascade), and the backplane is the
**opt-in upgrade for production / multi-user / multi-worker** — designed-in
behind a stable seam, never a prerequisite for adoption. Same app code; swap the
transport.

### 12.7 Dependencies

Sequencing and upstream/downstream risks, made explicit so the backplane is not
started before its prerequisites land.

| Dependency | Direction | Why it blocks / enables |
|---|---|---|
| **Single-node `signal()` (§1–11) — SHIPPED** | Upstream (done) | The backplane is a transport swap *behind* `SignalRegistry.bus`. Without the shipped registry/stream/contract there is nothing to back. |
| **The render-on-publish inversion (§12.2)** | Internal, blocks the seam | The shipped path recovers the payload from the per-process value cache (`signal_stream.py:87-92`). The protocol must render eagerly at `publish` and carry the payload in-band before any network adapter is correct. This is the one shipped-path behavior change and must land *with* the seam, not after. |
| **`chirp[redis]` extra — EXISTS** | Upstream (done) | `RedisSignalBus` reuses it. No new dependency for the first backplane. |
| **Shared state store (app's job, not Chirp's)** | Downstream caveat | The backplane fans out *notifications/rendered values*; it is **not** a data store (§12.4). A multi-worker app still needs shared source-of-truth (DB / Redis-as-store). The docs must say this loudly or users will expect the bus to replicate `wallet.balance`. |
| **Pure-derived contract (§12.3) — ENFORCED single-node** | Cross-cutting | Already true in the shipped build (`NotifFeed` refactor + transitive `_cascade`). The backplane *depends on* it staying true: a derived that reads process-local state is non-deterministic across workers. Any regression here silently corrupts multi-worker output. |
| **NATS / Postgres adapters** | Downstream (deferred) | Same protocol, different wire. Explicitly **not** first-backplane work; NATS needs a new `chirp[nats]` extra (a fresh stop-and-ask). |
| **Durable mode (`coalesce=False`)** | Downstream (deferred) | Needs an adapter capability + resume cursor (§12.5). Out of scope for the first backplane. |
| **HTTP/2 transport (pounce)** | Orthogonal | Connection-cap relief, unrelated to cross-worker fan-out. Neither blocks the other. |

### 12.8 Risks

| ID | Risk | Likelihood | Mitigation |
|---|---|---|---|
| **R1** | **Silent split-brain** — an app sets `workers>1` with `signal_bus="memory"` and realtime silently only reaches one worker's users (the §12.1 multi-user correctness bug). | High (it is the default `workers=0`/auto path) | The new `signal_bus_single_worker` contract check (§12.4): WARN in dev/staging, **ERROR in production**. Fail-loud, names the fix. This is the single most important guardrail. |
| **R2** | **Adapter selection fails open** — an unknown/misconfigured `signal_bus` falls back to in-process and reintroduces R1 silently. | Medium | Startup `ValueError` on unknown value; no silent fallback. Connection failure at adapter init surfaces at startup, not first emit. |
| **R3** | **Render-on-publish changes the hot path** — moving render from drain-time to publish-time (§12.2) could regress single-node latency or break per-event render isolation (`signal_stream.py` boundary). | Medium | Keep render-error isolation: a `publish` whose render raises caches the value and skips the wire (today's `render_for_emit` → `None` semantics), never poisoning the connection. Benchmark single-node before/after; the inversion is contained in `InProcessSignalBus`. |
| **R4** | **Redis reconnect gap loses an append-stream message** — coalescing-latest self-heals, but `coalesce=False` topics drop data across a reconnect. | Medium (only if durable mode is used on plain pub/sub) | Durable mode is explicitly deferred (§12.5); the live-value default self-heals. The first backplane ships live-value only; `coalesce=False` over Redis pub/sub must WARN or be rejected. |
| **R5** | **Pure-derived regression across workers** — a derived reads process-local state and emits a value that disagrees with the data it shipped (the original `notif_badge` bug). | Medium | The contract is documented (§12.3) but not yet *statically enforced*. Open question: can `app.check()` flag a derived `compute` that closes over a store reference? If not, this stays a documented discipline + review item. |
| **R6** | **`redis` accidentally imported at core import time** — breaks the optional-extra contract. | Low | Lazy import inside the adapter (the `cache/backends/redis.py` pattern); a `test_lazy_imports.py`-style assertion that `import chirp` does not import `redis`. |
| **R7** | **Audience / presence filtering lost in the network hop** — `ReactiveBus` does per-subscriber audience filtering (`bus.py:91-94`); a naive `PUBLISH signal:<topic>` fans out to everyone. | Medium | Per-user topics must encode audience in the channel name (`signal:<topic>:<user_id>`) or the adapter must re-apply audience after receive. Must be designed before per-user signals ride the backplane. |

### 12.9 Stop-and-Ask Surfaces (root `AGENTS.md`)

Per root `AGENTS.md` "Stop And Ask", **every** item below requires steward
sign-off **before code lands**. This section proposes the shape only.

| Surface | Root `AGENTS.md` trigger | Owning steward(s) | Collateral required |
|---|---|---|---|
| **`SignalBus` Protocol** (new plugin protocol) | "plugin protocols", "protocol shapes" | realtime | `docs/public-api.md` if exported; protocol-conformance test; changelog fragment |
| **`signal_bus` `AppConfig` field** (new public config flag) | "Adding a … `AppConfig` field … or public config flag" + "environment-variable parity when relevant" | app/state (`src/chirp/`) | `config.py` + `from_env` parity; `docs/public-api.md`; `docs/plan-appconfig-1-0-audit.md` cross-ref; changelog |
| **`app.set_signal_bus(...)` setter** (new public method, registry mutation) | "public API … top-level exports" | app/state | `_check_not_frozen` test; docs |
| **`RedisSignalBus` + `redis` extra reuse** (optional dependency) | "optional extra" + Optional-Dependencies cross-cutting concern | realtime + app/state | missing-extra import-error test; lazy-import test; install-command docs |
| **`signal_bus_single_worker` contract rule + new category** (new `app.check()` rule, env-aware severity) | "Promoting/demoting `app.check()` severities or changing default contract semantics" | contracts | `tests/contracts/` coverage (memory+multi-worker → WARN/ERROR); terminal-report category wiring; `site/content/docs/quality/contracts-debugging/categories.md` |
| **`ContractCheckSnapshot.signal_bus` field** (snapshot surface) | "free-threaded shared state" / contract snapshot | app/state + contracts | snapshot field test |
| **Render-on-publish inversion** (changes shipped single-node behavior) | "return-type semantics" / render pipeline near-miss; free-threaded shared state | realtime | single-node before/after behavior test; render-isolation test; changelog note (behavior-preserving but internal-contract change) |

> No backplane code is written until realtime **+** app/state **+** contracts
> stewards sign off, with the public-API and changelog collateral above moving in
> the same PR as the behavior. The Convergence Rule applies if two stewards flag
> the same surface.

### 12.10 Acceptance Criteria

What proof closes each phase (the `plan/AGENTS.md` "backlog items name proof"
requirement). None of this is built; these are the gates.

**Backplane phase (opt-in, first deliverable):**

- [ ] `SignalBus` `runtime_checkable` Protocol exists; `InProcessSignalBus` and
      `RedisSignalBus` both pass `isinstance(..., SignalBus)`.
- [ ] `signal_bus="memory"` is byte-for-byte behavior-identical to today on a
      single worker: the existing `signal()` / Lucky Cat tests pass unchanged.
- [ ] A **two-worker** integration test (or a two-`SignalRegistry`/two-bus
      simulation against one Redis) proves an `emit` on instance A reaches a
      `/_chirp/live` subscriber on instance B — the §12.1 correctness bug is fixed.
- [ ] Free-threading concurrency test for the adapter seam (Lock proof, root
      `AGENTS.md` Free-Threading requirement) — the `RedisSignalBus` subscribe
      iterator is safe under concurrent connects/disconnects.
- [ ] `import chirp` does **not** import `redis` (lazy-import assertion, R6).
- [ ] Missing-`redis` extra with `signal_bus="redis"` raises an actionable
      `pip install chirp[redis]` error, not an opaque `ImportError` (R6, optional
      -dependency contract).
- [ ] Unknown `signal_bus` value raises a startup `ValueError` naming the legal
      set (R2) — no silent in-process fallback.
- [ ] `signal_bus_single_worker` contract check fires: a
      `@pytest.mark.issue`-tagged test with a signal registered + `workers>1` +
      `signal_bus="memory"` → WARN (dev) / ERROR (production); clean when
      `workers=1` **or** `signal_bus="redis"`.
- [ ] Render-on-publish keeps render-error isolation: a topic whose render raises
      caches the value and emits nothing, never killing the shared connection (R3).
- [ ] Redis reconnect is transparent to the SSE consumer: a dropped broker
      connection self-heals (bounded backoff, re-subscribe) and the next publish
      reconciles every binding (live-value mode, R4).
- [ ] Public-API / changelog collateral lands in the same PR (towncrier fragment;
      `docs/public-api.md`; `categories.md`).
- [ ] A real-browser smoke (not just TestClient string-asserts — per the
      verify-in-browser feedback) of a two-worker Redis-backed app: user A's
      action updates user B's screen.

**Durable mode (later, explicitly deferred — not part of the first backplane):**

- [ ] `coalesce=False` over a durable adapter (Redis Streams / JetStream) with a
      resume cursor; no message loss across a forced reconnect.
- [ ] `coalesce=False` over plain pub/sub WARNs or is rejected at registration
      (R4).

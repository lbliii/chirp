---
title: Signals
description: Server-owned reactive values — declare once, bind many, over one SSE connection
draft: false
weight: 22
lang: en
type: doc
tags: [signals, sse, real-time, reactive, htmx]
keywords: [signal, derived, emit, server reactive values, signal_connect, sse-swap, one connection]
category: guide
---

## What Is A Signal?

A *signal* is a server-owned named value, declared once, that fans out over a
**single** shared SSE connection to **every** template binding that listens for
it. `{{ signal('balance') }}` in the topbar and `{{ signal('balance') }}` in a
modal both swap together from one `event: balance` on the wire.

That cardinality — one value, many bindings — is the thing plain OOB cannot
express. An OOB swap names one DOM id; a signal names a *value*, and htmx's
`sse-swap` matches every bound element with `querySelectorAll`. Declare the
producer once, bind the value anywhere, and update them all with one push.

```python
from chirp import App

app = App()


@app.signal("balance", initial=wallet.balance)
async def balance():  # push-only: driven by app.emit, yields nothing
    if False:
        yield 0


# ... later, in a mutation handler:
app.emit("balance", new_balance)   # every {{ signal('balance') }} updates
```

```html
<!-- topbar -->
<span class="token">{{ signal('balance') }}</span>

<!-- deposit modal, elsewhere on the page -->
<strong>{{ signal('balance') }}</strong>
```

Both bindings paint the current value server-side (no empty-then-fill flash),
then swap in lockstep on every `app.emit("balance", ...)` — from **one**
connection.

## When To Use A Signal

| You want… | Use |
|-----------|-----|
| One named value mirrored in many places, kept in sync from one push | **`signal()`** |
| A post-load event channel (notifications feed, chat tail, log stream) | `EventStream` |
| Slow initial-load data filled in after the shell paints | `Suspense` |
| The first paint to stream in section-by-section | `Stream` |

A signal is for *live values that appear more than once*: a balance, a ticker, an
unread badge, a connection-status pill. If a page opens several SSE scopes only to
keep a handful of shell values current — a count here, a strip there — fold them
onto signals and the page holds **one** connection instead of N.

If you have a one-directional event *stream* (append-only notifications, a chat
tail) rather than a *value*, reach for `EventStream` — see
[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]. For
data-mutation-to-block fan-out keyed by document scope, see the
[[docs/build-apps/streaming-updates/reactive-system|Reactive System]]; signals are
the thin, name-keyed surface built on the same bus.

## The Three Pieces

A signal-powered page wires three things:

1. **A producer** — `@app.signal(name, ...)` (a live value) or `@app.derived(name, on=(...))`
   (a value computed from other signals).
2. **The push** — `app.emit(name, value)` from a mutation handler, *or* an async
   `source` generator that yields successive values.
3. **The bindings** — `{{ signal('name') }}` / `{{ signal_block('name') }}`
   sinks, all living under one `{{ signal_connect() }}` wrapper.

### Producers — `@app.signal`

A primary signal has one producer. Drive it either by `app.emit` (push) or by an
async `source` generator (pull). Use the decorated function as the source:

```python
@app.signal("ticker", initial=first_spotlight, render=render_strip)
async def ticker():
    async for price in market.watch():
        yield price          # each yield renders + fans out as event: ticker
```

- `initial` — a zero-arg callable returning the SSR seed value, so a binding
  paints its current value with no flash.
- `render` — a `value -> str` mapper for the SSE `data:` payload and the seed
  (defaults to `str`). Return HTML to swap a fragment, text to swap a scalar.
- `coalesce` (default `True`) — latest-wins. A live value is idempotent, so
  dropping a stale update under back-pressure is safe; the next emit reconciles
  every binding. It also enables **emit dedup**: re-emitting a value equal to the
  current one is skipped (no wire event, no derived cascade) — a pure `render` maps
  equal values to equal payloads, so the swap would be byte-identical. Set `False`
  for append-style / drop-sensitive topics (e.g. a toast log) where every emit must
  fire even on a repeat value.

For a push-only value, pass nothing to yield — `app.emit` drives it:

```python
@app.signal("balance", initial=wallet.balance)
async def balance():
    if False:
        yield 0   # never runs; the framework pumps it once and emit() takes over
```

### Derived signals — `@app.derived`

A derived signal recomputes and re-emits whenever **any** of its dependencies
changes. `compute` receives the current dependency values positionally, in
declaration order:

```python
@app.derived("net_worth", on=("balance", "holdings"))
def net_worth(balance, holdings):
    return balance + holdings
```

Bind it like any signal: `{{ signal('net_worth') }}`. A single
`app.emit("balance", ...)` updates `balance` *and* re-derives `net_worth` in the
same cascade. Derived-of-a-derived propagates too.

### The pure-derived rule

A `derived`'s `compute` **must be a pure function of its input signal values**. It
must not read process-local state — no store lookups, no globals, no clocks. The
emitted value already carries everything the derived needs:

```python
# ✓ pure — reads only its input signal value
@app.derived("notif_badge", on=("notifications",), render=render_badge)
def notif_badge(feed):
    return feed.unread        # the snapshot bundled the count with the rows

# ✗ impure — re-reads a process-local store
@app.derived("notif_badge", on=("notifications",))
def notif_badge_bad(feed):
    return store.unread_count()   # non-deterministic across workers; races the bus
```

A store read is non-deterministic across workers and can race a concurrent
mutation on another thread, so the badge could disagree with the list it is meant
to summarize. Pass everything the derived needs *through the signal value* (a
snapshot that bundles the rows and the count together, captured atomically).

### Bindings — `signal()`, `signal_block()`, `signal_connect()`

Three template globals, registered automatically when any signal exists:

- `{{ signal('name') }}` — an SSR-seeded **scalar** sink:
  `<span sse-swap="name" hx-target="this">{seed}</span>`. The default `sse-swap`
  swap is `innerHTML`.
- `{{ signal_block('name') }}` — the same, for an HTML **fragment**, on a `<div>`.
  The seed is treated as already-rendered HTML (the signal's `render` produced
  markup).
- `{{ signal_attrs('name') }}` — the binding **attributes only**
  (`sse-swap="name" hx-target="this"`), for an **existing** element. The element
  keeps rendering its own SSR body; live events `innerHTML`-swap it. Use this when a
  `signal()`/`signal_block()` wrapper would break the element's own layout — e.g. a
  CSS-grid container whose direct children must stay grid items, or a `<ul>`:

  ```html
  <section class="board" {{ signal_attrs('market_stats') }}>
    {{ stat_strip_body(stats) }}   {# the section renders + re-renders its own body #}
  </section>
  ```
- `{{ signal_connect() }}` — the **one** shared connection wrapper. Place it once
  in the shell; every signal sink must live as a **descendant**.

```html
{{ signal_connect() }}
<header>
  <span class="balance">{{ signal('balance') }}</span>
  {{ signal_block('ticker') }}
</header>
<main id="main">
  {% block content %}{% end %}
</main>
</div>{# close the signal_connect() wrapper #}
```

> **Important**: `signal_connect()` emits an opening `<div hx-ext="sse"
> sse-connect="/_chirp/live" hx-disinherit="hx-target hx-swap">`. Every sink must
> be a descendant — htmx binds `sse-swap` via `querySelectorAll`, which excludes
> the connect element itself. Close the wrapper yourself after the last sink.

Prefer `{{ signal_attrs('name') }}` for binding an existing element — its call-site
is recorded for topic scoping and recognised by the contract, so the binding is
validated even though the `sse-swap` is produced at render time. A hand-written
`sse-swap="name"` attribute also works, but it is only contract-validated when it
sits in a template that *itself* opens the signal connect (a page composed into a
connect-bearing layout is not scanned), so `signal_attrs` is the safer choice.

The `/_chirp/live` merge stream is auto-registered at freeze when any signal
exists. It subscribes to every registered signal: an event with no matching
`sse-swap` on the current page is a harmless htmx no-op, so shell chrome stays
current on every page.

## Worked Example

A live $MEOW balance mirrored in the topbar and a deposit modal, plus a derived
net-worth line:

```python
from chirp import App, AppConfig

# SSE + cross-thread emits require async workers; an in-memory demo runs
# single-process (see PRODUCTION CONSTRAINT below).
app = App(config=AppConfig(worker_mode="async", workers=1))


@app.signal("balance", initial=lambda: wallet.balance, render=lambda v: f"{v:,} MEOW")
async def balance():
    if False:
        yield 0   # push-only


@app.derived("net_worth", on=("balance",), render=lambda v: f"≈ ${v / 100:,.2f}")
def net_worth(balance):
    return balance   # pure: derived from the emitted value only


@app.route("/deposit", methods=["POST"])
async def deposit(request):
    amount = int((await request.form())["amount"])
    wallet.balance += amount
    app.emit("balance", wallet.balance)   # topbar, modal, AND net_worth all update
    return Fragment("deposit.html", "deposit_form", ok=True)
```

```html
{{ signal_connect() }}
<header>
  $MEOW: <span class="token">{{ signal('balance') }}</span>
  <span class="net-worth">{{ signal('net_worth') }}</span>
</header>
<main id="main">
  {% block content %}{% end %}{# the deposit modal here also uses {{ signal('balance') }} #}
</main>
</div>{# close signal_connect() #}
```

One `app.emit("balance", ...)` fans `event: balance` to both balance bindings and
cascades into `net_worth` — all over a single connection.

## Recipe — a live board (one source, many derived projections)

To make several regions of a page update live from **one** data source over the
single connection, use one **source** signal as a clock-plus-snapshot and a
**derived** projection per region. Compute the expensive part (a ranking, a query)
**once** in the source; each derived is a cheap pure projection that re-renders its
own region in lockstep — the *compute-once / broadcast-many* shape.

```python
# ONE source samples the data on a human cadence and emits a self-contained
# snapshot (the data + per-value direction flags for the flash). It has no DOM
# sink of its own, so its render returns None to skip its own wire event.
@app.signal("board", initial=lambda: snapshot(None), render=lambda _v: None)
async def board():
    prev = None
    while True:
        await asyncio.sleep(1.5)          # the refresh cadence (throttle, don't firehose)
        prev = snap = snapshot(prev)      # read-only; carries dirs vs the previous snap
        yield snap

# Each region is a PURE projection of the one snapshot — recomputed + re-rendered
# in the same cascade, and skipped automatically when its projection is unchanged.
@app.derived("stats",  on=("board",), render=render_stats)
def stats(b):  return (b.stats, b.stat_dirs)

@app.derived("movers", on=("board",), render=render_movers)
def movers(b): return (b.movers, b.mover_dirs)
```

Bind each region with `signal_attrs` on the existing container, and render the same
`{% def %}` body for the SSR paint and the derived re-render so they never drift:

```html
<section class="stats" {{ signal_attrs('stats') }}>{{ stats_body(stats) }}</section>
<div class="movers" {{ signal_attrs('movers') }}>{{ movers_body(movers) }}</div>
```

Why it scales: the snapshot is built once per tick (not once per region); the
derived stay pure (deterministic across workers); emit dedup drops any region whose
projection didn't change; and it all rides the one `/_chirp/live` connection. The
Lucky Cat markets lobby (`examples/chirpui/lucky_cat`) is a full worked example — a
stat strip, a re-ranking movers grid, and a featured spotlight, all live.

> **Flash on change**: each region `innerHTML`-swaps, so its values/rows are
> re-created on every tick. Put a one-shot CSS animation class only on the values
> that actually changed direction (carried in the snapshot's `dirs`) — the freshly
> inserted element re-fires the animation, so only real movement flashes.

## PRODUCTION CONSTRAINT — single-process only

The signal bus is **in-process memory**. The `ReactiveBus` behind `@app.signal`
lives in one OS process, and the `/_chirp/live` SSE connection is pinned to the
worker that accepted it. This means the single-node `signal()` primitive that
ships today is **single-process only**:

- **Run `workers=1`.** With multiple OS-process workers, each holds a *separate*
  copy of the bus and the value cache. A push on one worker is invisible to the
  bindings served by another, and the long-lived `/_chirp/live` connection ties up
  one worker — page loads that land there can stall.
- **Use `worker_mode="async"`.** The merge stream is an async `EventStream`, and
  cross-thread emits ride the bus's `call_soon_threadsafe` delivery — the
  subscriber and the emitter must share one event loop. (See
  [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] →
  Worker Mode.)

This is the right shape for a single-user demo, an internal tool, or any app you
deploy as one process. **Multi-worker realtime needs a shared bus backplane**
(Redis / Postgres pub-sub) plus an external state store, so every worker sees the
same emits and the same current values. That pluggable multi-worker `SignalBus` is
designed but not yet shipped — it is forward-referenced in the live-SSE-topics RFC
(`plan/drafted/rfc-live-sse-topics.md`, §12), and the surface is classified
**Provisional** in `docs/public-api.md` until it lands.

If you need realtime across workers *today*, use product-owned transport: an
`EventStream` reading a durable cursor (a database sequence, a queue offset) per
the [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
replay pattern, where the backplane is your store rather than an in-process bus.

## Contract Validation

`app.check()` validates signal bindings against producers at startup:

| Check | Severity | What it catches |
|---|---|---|
| `signal_dead_binding` | ERROR | A `{{ signal('x') }}` / `signal_block('x')` / `signal_attrs('x')` (or an `sse-swap="x"` under the signal stream) with **no** registered producer — the element would never update (the dead-binding class) |
| `signal_orphan` | INFO | A registered signal that no template binds — produced but never displayed |

Because signal names are dynamic (`signal(name)`), this rule validates against the
authoritative producer registry rather than AST inference. See
[[docs/quality/contracts-debugging/categories|Contract Categories]].

## Next Steps

- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — `EventStream` basics and replay
- [[docs/build-apps/streaming-updates/reactive-system|Reactive System]] — scope-keyed fan-out for data mutations
- [[docs/build-apps/streaming-updates/sse-patterns|SSE Patterns]] — four update patterns
- [[docs/about/thread-safety|Thread Safety]] — free-threading guarantees behind the bus

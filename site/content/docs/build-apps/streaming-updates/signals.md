---
title: Signals
description: Server-owned reactive values — declare once, bind many, over one SSE connection
draft: false
weight: 22
lang: en
type: doc
tags: [signals, sse, real-time, reactive, htmx]
keywords: [signal, derived, emit, server reactive values, signal_connect, sse-swap, one connection, audience session]
category: guide
---

## What is a signal?

A *signal* is a server-owned named value. You declare it once, bind it
`{{ signal('balance') }}` in as many templates as you like, and one
`app.emit('balance', ...)` updates every binding at once — over a single shared
[[docs/build-apps/streaming-updates/server-sent-events|SSE]] connection.

Reach for a signal when the same live value appears in more than one place — a
balance in the topbar and in a modal, an unread badge, a connection-status pill —
and you want them all in lockstep from one push. That cardinality — one value,
many bindings — is the thing a plain OOB swap cannot express: an OOB swap names
one DOM id; a signal names a *value*.

:::{since} 0.8.0
The `signal()` / `derived()` / `emit()` surface is **Provisional**: it ships and
is supported, but may still settle. The single-node primitive is what's
documented here; a multi-worker backplane is in design.
:::

```python
from chirp import App

app = App()


@app.signal("balance", initial=lambda: wallet.balance)
async def balance():  # push-only: driven by app.emit, yields nothing
    if False:
        yield 0


# ... later, in a mutation handler:
app.emit("balance", new_balance)   # every {{ signal('balance') }} updates
```

```html
{{ signal_connect() }}            {# one shared connection wrapper #}
<header>
  <span class="token">{{ signal('balance') }}</span>          {# topbar #}
</header>
<main id="main">
  {% block content %}{% end %}    {# a modal here also binds {{ signal('balance') }} #}
</main>
</div>{# close the signal_connect() wrapper #}
```

Both bindings paint the current value server-side (no empty-then-fill flash),
then swap in lockstep on every `app.emit("balance", ...)` — from one connection.

## When to use a signal

A signal is for *live values that appear more than once*: a balance, a ticker, an
unread badge, a status pill. For other shapes of real-time update, reach for a
sibling type:

:::{list-table}
:header-rows: 1

* - You want…
  - Use
* - One named value mirrored in many places, kept in sync from one push
  - **`signal()`** (this page)
* - A post-load event channel — notifications feed, chat tail, log stream
  - [[docs/build-apps/streaming-updates/server-sent-events|`EventStream`]]
* - Slow initial-load data filled in after the shell paints
  - `Suspense`
* - The first paint to stream in section-by-section
  - `Stream`
:::

:::{tip} The connection-budget win
If a page opens several SSE scopes only to keep a handful of shell values current —
a count here, a strip there — fold them onto signals and the page holds **one**
connection instead of N.
:::

For data-mutation-to-block fan-out keyed by document scope, see the
[[docs/build-apps/streaming-updates/reactive-system|Reactive System]]; signals are
the thin, name-keyed surface built on the same bus.

## The three pieces

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
  dropping a stale update under back-pressure is safe.

For a push-only value, pass nothing to yield — `app.emit` drives it:

```python
@app.signal("balance", initial=lambda: wallet.balance)
async def balance():
    if False:
        yield 0   # never runs; the framework pumps it once and emit() takes over
```

:::{dropdown} Coalesce and emit dedup — when to set `coalesce=False`
`coalesce=True` (the default) also enables **emit dedup**: re-emitting a value
equal to the current one is skipped — no wire event, no derived cascade. A pure
`render` maps equal values to equal payloads, so the swap would be byte-identical
anyway.

Set `coalesce=False` for append-style or drop-sensitive topics — a toast log, an
event ticker — where every emit must fire even on a repeat value, and where you
never want an update dropped under back-pressure.
:::

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

### Bindings — `signal()`, `signal_block()`, `signal_connect()`

Three template globals, registered automatically when any signal exists:

The examples below describe the default htmx 2 tier. On the exact htmx 4
preview, the same helpers emit `data-chirp-signal="name"` on each sink and one
`hx-sse:connect` wrapper. An unnamed `<hx-partial>` targets all matching markers,
so repeated sinks, SSR seeds, topic scoping, and `signal_bind()`'s wrapper-free
layout contract stay the same.

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
  in the shell. Every signal sink must live as a **descendant**, and you close the
  wrapper yourself after the last sink.

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

Prefer `{{ signal_bind('name') }}` (`signal_attrs` remains an alias) for binding an existing element: its call-site
is recorded for topic scoping and recognised by the contract, so the binding is
validated even though the `sse-swap` is produced at render time. A hand-written
`sse-swap="name"` attribute also works, but it is only contract-validated when the
template either opens the connect itself or is composed under a layout that does.

:::{dropdown} Inside `signal_connect()` — the markup and the subscribe-all rule
`signal_connect()` emits an opening legacy
`<div hx-ext="sse" sse-connect="/_chirp/live" hx-disinherit="hx-target hx-swap">`
(or `<div hx-sse:connect="/_chirp/live">` on the exact htmx 4 preview)
(session-scoped signals append `?aud=<key>` — see below). htmx binds `sse-swap`
via `querySelectorAll`, which excludes the connect element itself, so every sink
must be a *descendant* of the wrapper.

The `/_chirp/live` merge stream is auto-registered at freeze when any signal
exists, and it subscribes to **every** registered signal. An event with no
matching `sse-swap` on the current page is a harmless htmx no-op, so shell chrome
stays current on every page without per-page topic configuration.
:::

## Per-visitor signals — `audience="session"`

By default a signal is **global**: one value, fanned to every connection. For a
value that differs per visitor — a logged-in user's balance, their unread count —
declare it with `audience="session"` so each connection sees only its own value:

```python
@app.signal("balance", audience="session")
async def balance():
    if False:
        yield 0   # push-only


@app.route("/deposit", methods=["POST"])
async def deposit(request: Request):
    amount = int((await request.form())["amount"])
    new_balance = credit(request, amount)
    app.emit("balance", new_balance, audience_key=session_key(request))
    return Fragment("deposit.html", "deposit_form", ok=True)
```

`emit` takes an `audience_key` (the visitor's session store key) for session
signals; `signal_connect()` renders the tier's connection attribute with
`/_chirp/live?aud=<key>` so the
bus fans that emit only to the matching connection.

:::{note}
Session-scoped signals resolve their audience key from the session, so they
require `SessionMiddleware`. Without it the key is never available and per-visitor
fan-out silently breaks — `app.check()` raises this as a `signal_scope` ERROR (see
[[docs/quality/contracts-debugging/categories|Contract Categories]]).
:::

## Gotcha — derived `compute` must be pure

A `derived`'s `compute` **must be a pure function of its input signal values**. The
emitted value already carries everything the derived needs; re-reading
process-local state silently races the bus.

:::{danger}
```python
# WRONG — re-reads a process-local store inside a derived
@app.derived("notif_badge", on=("notifications",))
def notif_badge_bad(feed):
    return store.unread_count()   # non-deterministic; races the bus

# CORRECT — read only the input signal value
@app.derived("notif_badge", on=("notifications",), render=render_badge)
def notif_badge(feed):
    return feed.unread            # the snapshot bundled the count with the rows
```
:::

:::{dropdown} Why an impure derived bites
A store read is non-deterministic across workers and can race a concurrent
mutation on another thread, so the badge could disagree with the list it is meant
to summarize.

Pass everything the derived needs *through the signal value* — a snapshot that
bundles the rows and the count together, captured atomically. See
[[docs/about/thread-safety|Thread Safety]] for the free-threading guarantees
behind the bus.
:::

## Worked example

A live $MEOW balance mirrored in the topbar and a deposit modal, plus a derived
net-worth line.

:::{example} Live balance with a derived net-worth
```python
from chirp import App, AppConfig, Fragment, Request

# SSE + cross-thread emits require async workers; an in-memory demo runs
# single-process (see Production constraint below).
app = App(config=AppConfig(worker_mode="async", workers=1))


@app.signal("balance", initial=lambda: wallet.balance, render=lambda v: f"{v:,} MEOW")
async def balance():
    if False:
        yield 0   # push-only


@app.derived("net_worth", on=("balance",), render=lambda v: f"≈ ${v / 100:,.2f}")
def net_worth(balance):
    return balance   # pure: derived from the emitted value only


@app.route("/deposit", methods=["POST"])
async def deposit(request: Request):
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
:::

### One source, many derived projections

To make several regions update live from **one** data source over the single
connection, use one **source** signal as a clock-plus-snapshot and a **derived**
projection per region. Compute the expensive part (a ranking, a query) **once** in
the source; each derived is a cheap pure projection that re-renders its own region
in lockstep — the *compute-once / broadcast-many* shape.

```python
import asyncio

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
@app.derived("stats", on=("board",), render=render_stats)
def stats(b):
    return (b.stats, b.stat_dirs)


@app.derived("movers", on=("board",), render=render_movers)
def movers(b):
    return (b.movers, b.mover_dirs)
```

Bind each region with `signal_attrs` on the existing container, and render the same
`{% def %}` body for the SSR paint and the derived re-render so they never drift:

```html
<section class="stats" {{ signal_attrs('stats') }}>{{ stats_body(stats) }}</section>
<div class="movers" {{ signal_attrs('movers') }}>{{ movers_body(movers) }}</div>
```

The snapshot is built once per tick (not once per region); the derived stay pure
(deterministic across workers); emit dedup drops any region whose projection
didn't change; and it all rides the one `/_chirp/live` connection. The
[[docs/examples/lucky-cat|Lucky Cat example]] markets lobby is a full worked
version — a stat strip, a re-ranking movers grid, and a featured spotlight, all
live.

:::{tip} Flash only what changed
Each region `innerHTML`-swaps, so its values are re-created on every tick. Put a
one-shot CSS animation class only on values whose direction actually changed
(carried in the snapshot's `dirs`) — the freshly inserted element re-fires the
animation, so only real movement flashes.
:::

## Production constraint — single-process only

The signal bus is **in-process memory**, and the `/_chirp/live` SSE connection is
pinned to the worker that accepted it. The single-node `signal()` primitive that
ships today is **single-process only**:

:::{warning}
- **Run `workers=1`.** With multiple OS-process workers, each holds a *separate*
  copy of the bus and value cache: a push on one worker is invisible to bindings
  served by another, and the long-lived connection ties up a worker so page loads
  that land there can stall.
- **Use `worker_mode="async"`.** The merge stream is an async `EventStream`, and
  cross-thread emits ride the bus's threadsafe delivery — the subscriber and the
  emitter must share one event loop. (See
  [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] →
  Worker Mode.)
:::

This is the right shape for a single-user demo, an internal tool, or any app you
deploy as one process. **Multi-worker realtime needs a shared bus backplane**
(Redis / Postgres pub-sub) plus an external state store, so every worker sees the
same emits and the same current values. That pluggable multi-worker bus is
designed but not yet shipped.

If you need realtime across workers *today*, use product-owned transport: an
`EventStream` reading a durable cursor (a database sequence, a queue offset) per
the [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
replay pattern, where the backplane is your store rather than an in-process bus.

## Contract validation

`app.check()` validates signal bindings against producers at startup:

:::{list-table}
:header-rows: 1

* - Check
  - Severity
  - What it catches
* - `signal_dead_binding`
  - ERROR
  - A `{{ signal('x') }}` / `signal_block('x')` / `signal_attrs('x')` (or an
    `sse-swap="x"` under the signal stream) with **no** registered producer — the
    element would never update.
* - `signal_orphan`
  - INFO
  - A registered signal that no template binds — produced but never displayed.
* - `signal_scope`
  - ERROR / WARNING
  - ERROR: an `audience="session"` signal with no `SessionMiddleware`. WARNING: a
    derived signal that depends on both global and session-scoped signals.
:::

Because signal names are dynamic (`signal(name)`), these rules validate against the
authoritative producer registry rather than AST inference. See
[[docs/quality/contracts-debugging/categories|Contract Categories]].

:::{note} See also

- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — `EventStream` basics and replay
- [[docs/build-apps/streaming-updates/reactive-system|Reactive System]] — scope-keyed fan-out for data mutations
- [[docs/build-apps/streaming-updates/sse-patterns|SSE Patterns]] — four update patterns
- [[docs/about/thread-safety|Thread Safety]] — free-threading guarantees behind the bus
:::

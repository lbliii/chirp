# RFC — Scoped (per-session / per-connection) signals

**Status**: Historical, partially implemented design. Session audiences,
audience-keyed values, derived inheritance, and the `signal_scope` checks shipped;
per-connection scope remains not now. The single-node history lives in
`rfc-live-sse-topics.md`; [RFC 023](../../docs/rfcs/023-private-signal-backplane.md)
owns the accepted, not-yet-shipped multi-worker data plane.

## Problem

`@app.signal` / `@app.derived` fan **one** value to **every** connection. There is
no scoping primitive, so per-user reactive state has no correct home:

- **`balance`** (Lucky Cat) is push-only via `app.emit("balance", v)` — but `emit`
  fans to *all* subscribers, so it would broadcast one user's balance to everyone.
- **The watchlist preview** is per-session; a global `watchlist` signal would show
  one user's stars to all. The reactive-lobby work left it **static** for exactly
  this reason.
- **A per-page-pinned featured** can't be honoured by a global source generator, so
  the spotlight had to track the *global* top gainer instead.

The single-node demo only stays correct because it runs `workers=1` and is
effectively single-user. Under real multi-user (even single-node), these leak.
Discovered building the reactive Markets lobby (see
`examples/chirpui/lucky_cat`, `.context/luckycat-reactive-friction-ledger.md` #1).

## Design sketch

Add a **scope key** dimension to the signal substrate. A scope key identifies the
audience of a value (default: the global scope `""`, today's behaviour).

1. **Declaration** — `@app.signal("balance", scope="session")` (and `"connection"`,
   `"global"`). `scope` selects how the key is derived per request/connection.
2. **Scoped value cache** — `SignalRegistry._values` keyed by `(scope_key, name)`
   instead of `name`. `current_rendered(name, scope_key)` seeds per request.
3. **Scoped emit** — `app.emit("balance", v, scope_key=session_id)`. The push only
   fans to subscribers whose connection resolves to that scope key. For source-
   driven scoped signals, the source factory is instantiated **per scope** (one
   generator per connection/session) rather than once globally.
4. **Bus scoping** — the `ReactiveBus` scope becomes `signal:{scope_key}:{name}`;
   the `/_chirp/live` stream subscribes only the scope keys for *its* connection
   (its session id + its connection id + global).
5. **SSR seed** — `signal()/signal_block()/signal_attrs()` resolve the current
   request's scope key (from the session middleware / a connection id in the
   request scope) when reading the seed.
6. **Derived** — a derived inherits the *narrowest* scope among its deps (a derived
   of a session signal is session-scoped); cascade runs within a scope key.
7. **Contract** — a `signal_scope` rule: a `scope="session"` signal requires
   `SessionMiddleware`; emitting a scoped signal without a resolvable key is an
   ERROR; mixing global + session deps in one derived is a WARNING.

## Seams touched

`src/chirp/realtime/signals.py` (value cache key, emit/cascade signature),
`signal_stream.py` (per-connection scope-key subscription set), `signal_globals.py`
(scope-key resolution at seed time), `app/__init__.py` (`emit(..., scope_key=)`,
`signal(scope=)`), `contracts/rules_signals.py` (new `signal_scope` rule).

## Why deferred from the reactive-lobby PR

This changes the **core data model** of every signal (cache key, emit signature,
bus scope, stream subscription) that the shipped `balance` / `ticker` /
`notifications` signals and the reactive lobby all depend on. Per the
[RFC 023](../../docs/rfcs/023-private-signal-backplane.md) gate, signal-core changes route through the realtime +
app/state + contracts stewards with public-API + changelog collateral before
landing. Cramming it into the lobby PR would make a large, risky change and couple a
showcase to an unproven core change. Ship the lobby + the small, additive fixes
(`signal_attrs`, emit dedup) first; land scoped signals as its own reviewed PR.

## Interaction with RFC 023 (multi-worker backplane)

Orthogonal but composable: a scope key is an input to RFC 023's opaque,
server-authorized broker subject. The browser never supplies or sees that key.

# RFC 023: Private multi-worker signal backplane

**Status:** Implemented by runtime child #699

**Decision issue:** [#678](https://github.com/lbliii/chirp/issues/678)

**Parent epic:** [#617](https://github.com/lbliii/chirp/issues/617)

**Runtime child:** [#699](https://github.com/lbliii/chirp/issues/699)

**Last audited:** 2026-07-10

**Shipping impact:** The private memory/Redis runtime, server-authorized routing,
and `signal_bus_single_worker` contract ship without a `SignalBus` export, new
`AppConfig` field, public setter, or custom adapter hook.

## Summary

Chirp's shipped `signal()` / `@app.derived` / `app.emit` surface uses a
process-local `ReactiveBus`. An emit on instance A therefore cannot wake an SSE
connection pinned to instance B. The first multi-worker increment will put a
private memory-or-Redis data plane behind the existing signal registry and
`/_chirp/live` route without changing `EventStream` semantics or creating a
generic broadcast API.

The accepted boundary is deliberately narrow:

- freeze selects a private memory backplane when `AppConfig.redis_url` is empty
  and a private Redis Pub/Sub backplane when it is set;
- the emitting instance caches the raw value, renders the registered signal
  value once, and publishes client-neutral rendered HTML;
- the receiving instance supplies the existing `_SignalUpdate` to the existing
  SSE/htmx dialect boundary;
- delivery is bounded coalescing-latest and at-most-once;
- the HTTP/EventSource connection owns reconnect, with no broker retry loop,
  replay, cursor, or ordering guarantee;
- audience identity is derived from trusted server session state, never from a
  client `aud` query parameter;
- Redis subjects are opaque, versioned HMACs and never appear in browser URLs,
  logs, traces, errors, or public inspection; and
- production `app.check()` fails when registered signals use the process-local
  backplane with an effective multi-worker launch posture.

## Pre-implementation audit

Before #699, `SignalRegistry.bus` was only a `ReactiveBus`. `SignalRegistry.emit()`
stores a raw value, emits a marker, and the SSE drain reads the latest local
cache value before rendering. This makes one slow local subscriber converge on
the latest cached value, but a remote process has neither the marker's cache nor
the rendered value.

The old `/_chirp/live` route accepted public `topics=` and `aud=` query
parameters. `signal_connect()` writes the raw session audience key into the
browser URL, and the route trusts that value. Unknown requested topics fall
back to subscribe-all. That shape is not accepted for a broker boundary. The
runtime child must remove it rather than encode it into Redis.

Async `source=` producers are connection-owned today: every live connection
starts and cancels its own source pump. They are not deployment-wide leaders.
The first Redis increment must preserve that ownership and must not turn every
browser connection into a Redis publisher.

## Accepted private shape

The names below are illustrative underscore-private names. They describe field
and ownership contracts, not public API.

```python
@dataclass(frozen=True, slots=True)
class _SignalBackplaneDescriptor:
    backend: Literal["memory", "redis"]
    process_local: bool
    supports_append: bool


@dataclass(frozen=True, slots=True)
class _SignalBackplanePlan:
    descriptor: _SignalBackplaneDescriptor
    redis_url: str | None = field(default=None, repr=False)
    subject_key: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _SignalPublication:
    name: str
    subject: str
    data: str = field(repr=False)
```

The compiler creates one `_SignalBackplanePlan` while the app is still mutable:

1. no registered signals means no backplane plan or connection;
2. registered signals plus an empty `config.redis_url` selects memory;
3. registered signals plus a non-empty `config.redis_url` selects Redis;
4. Redis selection requires the existing `chirp[redis]` extra and a shared,
   non-empty production `secret_key`; and
5. any invalid or unavailable Redis setup fails startup. It never falls back to
   memory.

The plan is bound to the registry exactly once before the framework signal route
is compiled, and its redacted descriptor is published atomically with runtime
state. A second bind or a post-freeze swap raises. The built-in contract checker
may receive the descriptor through an underscore-private frozen field or
internal checker input; third-party checks do not receive a new public snapshot
field.

This slice intentionally adds no `AppConfig.signal_bus`, no
`app.set_signal_bus()`, no exported or `runtime_checkable` protocol, and no
custom-adapter hook. `AppConfig.redis_url` / `CHIRP_REDIS_URL` is the only Redis
selection input for the first implementation. The runtime child must document
that existing apps which set `redis_url` and register signals will start the
Redis backplane.

## Lifecycle and ownership

The application lifespan owns the selected adapter coordinator.

1. Freeze publishes the immutable plan.
2. Internal startup opens the adapter before user startup hooks. A partial
   failure closes anything already opened and fails readiness.
3. The Redis publisher uses a thread-safe synchronous client or a safe loop
   handoff so `app.emit()` remains callable from sync and free-threaded paths.
4. Each Redis subscription is owned by the SSE iterator/event loop that created
   it. Exact subjects are subscribed after request authorization and released in
   the iterator's `finally` block.
5. Internal shutdown stops new publications, closes active local subscription
   iterators, waits for their cleanup, then closes Redis clients. Close is
   idempotent.
6. User shutdown hooks run while the adapter is still available; adapter close
   follows them. TestClient exercises the same internal startup/shutdown path.

The registry lock protects the raw cache and immutable registration reads only.
Rendering, Redis I/O, loop handoff, callbacks, and iterator close never occur
while that lock is held. A publish racing shutdown fails visibly and never
falls back to a process-local delivery path.

`app.kick_user` remains worker-local. Distributed cancellation requires a
separate owner/lease control plane and remains tracked by
[#384](https://github.com/lbliii/chirp/issues/384).

## Server-authorized routing

The browser may name public signals already visible in `sse-swap` /
`data-chirp-signal`, but it never supplies an audience key or a broker subject.

On `/_chirp/live`:

1. reject any legacy or forged `aud` parameter;
2. parse every requested public signal name and return 400 for an unknown name;
   never turn an invalid or empty scoped request into subscribe-all;
3. derive the session audience from `SessionSignalMiddleware` and trusted
   request/session state;
4. return 403 when a session-scoped signal is requested without its authorized
   server-side audience; and
5. map each authorized `(audience kind, audience key, signal name)` tuple to one
   exact opaque Redis subject.

The subject function is stable across instances with the same `secret_key`:

```text
subject = "chirp:signal:v1:" + base64url(
    HMAC-SHA256(
        secret_key,
        "chirp-signal-v1\0" + audience_kind + "\0" + audience_key + "\0" + signal_name,
    )
)
```

Redis uses exact `SUBSCRIBE`, never `PSUBSCRIBE signal:*`. The subscriber keeps
the authorized subject-to-public-name map in local memory, so the Redis payload
can be the rendered UTF-8 data alone. Neither the raw audience key nor the raw
signal name is required in the broker channel or payload.

Logs, errors, terminal checks, DevTools traces, and publication `repr` output may
record the public signal name and `global`/`session` scope. They must not record
the raw audience key, subject digest, rendered payload, Redis URL, or secret.
Rotating `secret_key` invalidates active subscriptions; normal HTTP reconnect
reauthorizes and derives the new subjects.

## Render and publish ordering

Imperative `app.emit()` and its derived cascade use this exact ordering:

1. validate the registered signal and server-side audience;
2. update the emitting registry's raw cache under its lock;
3. release the lock;
4. render through the registered signal/derived renderer;
5. if render fails, log the public signal name and scope, publish nothing, keep
   the cached raw value for SSR, and preserve the existing non-raising render
   failure behavior; and
6. publish `_SignalPublication` through the selected adapter.

A Redis publish failure raises a private runtime error to the `app.emit()`
caller after the local cache update. It does not retry internally and does not
deliver only to local subscribers. This is fail-loud at-most-once behavior, not
transactional coupling between application state and UI delivery.

The receiving worker never deserializes an arbitrary Python value, updates its
raw signal cache, or recomputes derived values. It turns the authorized broker
publication into the existing `_SignalUpdate(name, data)`. Existing server code
then chooses htmx 2 named-event framing or htmx 4 targeted-partial framing and
keeps per-event framing failures isolated.

Remote SSR still requires application-owned shared state or request-time
reseeding. Redis Pub/Sub is a wake-up/data plane, not the source of truth.

## Connection-owned sources

`source=` async generators remain local to the SSE connection in the first
Redis slice. Source yields and their derived cascade bypass the distributed
publisher and feed only the owning connection's local delivery path. Disconnect
cancels and awaits the source exactly as it does today.

The two-instance acceptance proof is therefore an imperative `app.emit()` on A
reaching a client connected to B. Deployment-wide source leadership, leases,
and republishing are not inferred from the data plane. They remain not-now work
behind the owner/lease lifecycle tracked by
[#385](https://github.com/lbliii/chirp/issues/385).

## Delivery, backpressure, and reconnect

The accepted Redis mode supports live values only:

- **at-most-once:** a publication can be missed during failure or disconnect;
- **coalescing-latest:** each subscriber has one pending slot per authorized
  subject, and a newer pending value replaces the older value for that subject;
- **bounded memory:** queue growth is bounded by the number of subjects the
  connection was authorized to subscribe to, not by publication rate;
- **no ordering:** delivery order across subjects is unspecified;
- **no replay:** no `Last-Event-ID`, cursor, stream, or backlog is added; and
- **no transparent broker reconnect:** a Redis read failure ends the iterator
  and SSE response. EventSource/htmx opens a fresh HTTP request, which is
  authorized again and creates fresh exact subscriptions.

A value published only during a gap can remain absent until the application
re-emits it or a page reseeds from shared state. The adapter does not claim that
the next connection receives the current value.

The existing `coalesce=False` append-style mode is not supported by Redis
Pub/Sub. Redis selection plus a distributed imperative emit for such a signal
must fail with actionable guidance; it must not silently drop append events.
Memory behavior remains unchanged. Durable append delivery is not part of this
RFC.

## Production contract

The runtime child adds built-in category `signal_bus_single_worker`. It runs
whenever signals are registered, even with no Kida loader or scannable template.
It reads the private frozen descriptor plus a private effective launch posture,
not mutable registry state.

The effective worker count must be the value actually passed to Pounce. A CLI
`--workers` override must therefore reach the same internal preflight. In
production/deploy posture, `workers=0` means auto/multi-worker intent and is
unsafe with the memory backplane; it is not resolved from the audit machine's
CPU count.

Severity matrix:

| Posture | Process-local + signals + workers |
| --- | --- |
| production or `deploy=True` | ERROR for `0` or `>1` |
| staging | WARNING for `0` or `>1` |
| development | silent for default `0`; WARNING only for explicit `>1` |
| any posture | clean for `1`, Redis, or no registered signals |

The diagnostic uses the existing `ContractIssue.message` and `details` fields.
For `workers=0`, render the subject value as `0 (auto)`.

Exact message:

```text
Signals use a process-local bus with workers={workers}; realtime updates cannot reach clients connected to another worker.
```

Exact details/fix:

```text
Set AppConfig(workers=1), or configure AppConfig(redis_url=...) / CHIRP_REDIS_URL for the private Redis signal backplane and keep signal source state in a shared store before deploying.
```

The rule is wired outside template scanning. Terminal and structured check
presentations retain the wording and group the category under Realtime.

## Runtime child proof

The implementation child [#699](https://github.com/lbliii/chirp/issues/699)
must include all of the following before
the backplane is described as shipped:

- private frozen/slotted plan, descriptor, and publication records;
- no new `AppConfig` field, top-level export, public setter, public protocol, or
  non-private contract snapshot field;
- memory selection and existing signal/source tests unchanged;
- Redis selection from existing `redis_url`, lazy import, missing-extra install
  guidance, startup-failure cleanup, and no `redis` import from `import chirp`;
- two Chirp instances behind Pounce `RoundRobinTestProxy`, with an imperative
  emit on A delivering rendered htmx 2 and htmx 4 output through B;
- generated browser URLs without `aud`, forged/legacy audience rejection, 400
  for unknown topics, 403 for unauthorized session topics, two-audience
  isolation, exact Redis subjects, and no audience/payload leakage in logs,
  errors, traces, or inspection;
- two instances with the same secret deriving the same subject;
- render-on-publish parity, render-failure isolation, visible Redis publish
  failure, and no remote raw-cache mutation or derived recomputation;
- source pumps remaining connection-local with no Redis publish, plus disconnect
  cancellation and existing bounded restart behavior;
- saturation proof that the newest pending value replaces an older one and
  memory stays bounded by authorized subject count;
- forced Redis read disconnect closing the SSE response, a fresh HTTP reconnect
  resubscribing, no replay, and the next application emit delivering;
- actionable rejection of Redis append-style (`coalesce=False`) publishes;
- idempotent startup/shutdown, active-stream cleanup, publish-versus-close race,
  and Python 3.14t concurrent publish/subscribe/disconnect stress with no lock
  held across network I/O or await;
- contract matrix for no signals; memory/Redis; workers `0`, `1`, and `2`;
  development/staging/production/deploy; no-template apps; deploy config
  immutability; and CLI worker overrides; and
- category docs, realtime production docs, public-status wording, optional-extra
  install guidance, and a changelog fragment in the runtime PR.

## Not now

- public `SignalBus` or generic broadcast API;
- `AppConfig.signal_bus`, public setter, custom adapter hook, or top-level bus
  exports;
- EventStream return-type or framing changes;
- NATS, Postgres LISTEN/NOTIFY, or SQLite polling adapters;
- Redis Streams, durable append delivery, replay, cursors, ordering,
  at-least-once, or exactly-once guarantees;
- deployment-wide async-source leadership or leases;
- distributed `kick_user` or another control-plane command channel;
- source-of-truth replication; and
- job-progress projection before the durable-job phases define it.

## Steward synthesis

Realtime, contracts, planning, and narrative-docs stewards independently agreed
that the old §12 public protocol/config proposal must not be promoted. The
audience-query finding converged at P0: the accepted design removes client
authority over audience identity and requires opaque server-side broker routing.

Accepted findings are reflected in the private freeze shape, server-authorized
routing, exact production diagnostic, effective-worker matrix, connection-local
source boundary, render ordering, backpressure, reconnect, lifecycle, and proof
sections above.

Deferred findings are the items in **Not now**. No steward requested a public
surface in this phase. Human review remains required because the repository has
no CODEOWNERS file.

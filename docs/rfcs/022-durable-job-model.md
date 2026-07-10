# RFC 022: Durable job model

**Status:** Proposed

**Issue:** [#615](https://github.com/lbliii/chirp/issues/615)

**Parent saga:** [#614](https://github.com/lbliii/chirp/issues/614)

**Last audited:** 2026-07-09

**Shipping impact:** None. This RFC does not add a public API, database table,
migration, runtime executor, AppConfig field, CLI command, contract category,
severity change, scheduler, cancellation protocol, or non-Postgres backend.

## Summary

Chirp should eventually provide a small Postgres-backed durable job primitive
for work that must survive process restart and be claimed safely across
instances. It is a job store and executor, not a workflow engine.

The first implementation should provide:

- typed, JSON-safe payload snapshots associated with stable handler identities;
- queue-scoped idempotency keys and explicit at-least-once semantics;
- atomic Postgres claims using `FOR UPDATE SKIP LOCKED`;
- owner and lease-token fencing for heartbeat, completion, retry, and failure;
- bounded attempts with explicit retry/backoff policy;
- priorities and database-coordinated per-queue concurrency limits;
- terminal failed records as the first dead-letter surface; and
- advisory JSON-safe progress shaped around `status`, `step`, and `total`.

The schema must ship as a normal, reviewable migration. The job feature must
never create or alter its tables automatically. A first executor runs in the
application deployment and uses the database for durability and coordination;
it does not require Redis or a separate worker service.

This RFC records semantics and proof obligations only. Exact Python names,
module placement, SQL schema, default values, contract categories, lifecycle
wiring, and compatibility status remain implementation-review decisions.

## Current implementation audit

This section describes `main` at `063cb23f`. It does not describe shipped job
behavior.

### No first-party durable-job runtime

There is no `JobStore`, job-definition registry, enqueue operation, claim loop,
or durable-job contract rule in `src/chirp/`. The README currently says that
background jobs integrate at framework seams rather than claiming a built-in
job system.

`App.render()` mentions background jobs as one possible caller of the existing
template-rendering helper. That helper freezes the app and renders Chirp return
values; it does not persist, claim, retry, lease, or execute work.

### Database and transaction foundation

`src/chirp/data/database.py` already supplies an async `Database` with
parameterized `fetch_one()`, `execute()`, and `transaction()` operations.
Transaction connections are task-local through a `ContextVar`. PostgreSQL uses
the in-tree Pelt pool, while SQLite serializes write transactions separately.

Rows map to typed dataclasses, and the data steward recommends frozen/slotted
read models. The PostgreSQL driver includes JSON/JSONB codecs. These are useful
implementation foundations, but none currently defines job semantics.

The `data-pg` optional dependency group is empty because the PostgreSQL driver
is in-tree. This does not authorize importing job/database behavior from core
HTML-only paths. Optional-domain isolation still needs proof.

### Reviewable migrations

`src/chirp/data/migrate.py` discovers numbered SQL files, applies them forward
in version order, records checksums, and rejects edits to applied migrations.
`chirp migrate` already applies those checked-in files as a one-shot deployment
operation. App startup can also apply the configured migration directory unless
the existing skip-migrations policy delegates that work to deployment.

The durable-job schema should use this migration surface. “Use the database”
does not mean that a store constructor may run `CREATE TABLE IF NOT EXISTS`.

### Lifecycle and free-threading boundary

`src/chirp/app/lifecycle.py` connects the configured database during lifespan
startup, runs setup hooks, flips readiness only after startup succeeds, then
drains shutdown hooks before disconnecting the database. Separate worker
startup and shutdown hooks are registered during setup and invoked by Pounce
worker lifecycle messages.

Those hooks are possible executor seams, not an approved integration. Starting
one poller per process, per Pounce worker, or per queue has different capacity
and shutdown behavior. The implementation must choose one model explicitly and
prove it under Python 3.14t instead of inferring ownership from hook names.

### Contract/compiler boundary

`ContractCheckSnapshot` is a frozen read model populated after app setup. It
contains registries and compiler facts required by current checks, but no job
definitions. `app.check()` therefore cannot currently verify a job handler,
payload type, queue, retry policy, or migration.

A future job-definition registry belongs to setup/freeze. Runtime enqueue must
reference a frozen definition by stable identity; it must not register handlers
after freeze. Adding snapshot fields, compiler records, or a new error category
requires its own contract design review.

### Progress is not HTML streaming

RFC 014 already separates Milo `Progress` from Chirp `Stream`, `Suspense`, and
`EventStream`. A local audit of installed `milo-cli` 0.4.1 found a frozen,
slotted `Progress(status, step=0, total=0)` value.

That three-field semantic shape is a useful interoperability reference, but
this RFC does not approve coupling the job model to Milo's type or validation
semantics. Persisted progress remains advisory job metadata. An application may
later project it into normal rendered HTML/SSE or Milo protocol notifications
without making the job store a JSON application endpoint.

## Approved direction

The [maintainer decision on #615][issue-615-decision] approves a provisional
Postgres-first store and the following boundaries:

- immutable job identity, definition reference, payload, queue, priority,
  idempotency key, and attempt policy;
- `pending`, `running`, `succeeded`, and `failed` lifecycle states;
- atomic `FOR UPDATE SKIP LOCKED` claims;
- owner plus opaque lease-token fencing;
- bounded attempts and retry/backoff;
- queue-scoped idempotency;
- advisory JSON-safe progress;
- at-least-once execution; and
- reviewable migrations rather than automatic schema mutation.

The first slice explicitly excludes a scheduler, cancellation, arbitrary object
serialization, SQLite or another backend, a top-level stable export, a new
AppConfig field, and a workflow JSON API.

## Terminology

- **definition** — setup-time handler metadata with a stable name, payload
  contract, queue policy, and retry policy;
- **job** — one immutable request to invoke a definition with a payload;
- **attempt** — one claimed invocation of the handler;
- **claim** — the atomic transition that grants one owner a running attempt;
- **owner** — one executor identity used for operations and diagnostics;
- **lease token** — an unpredictable per-claim fencing value;
- **lease** — the database-clock interval during which that token may renew or
  settle the attempt;
- **settle** — transition a running attempt to success, retry, or terminal
  failure;
- **dead letter** — a terminal `failed` job retained for inspection; and
- **progress** — advisory, replaceable metadata that never establishes state or
  ownership.

The definition and job are distinct. Deploying code can change the registered
definition while old payload snapshots remain in the database, so definition
and payload compatibility must be explicit.

## Core invariants

1. A job references exactly one stable definition identity.
2. Definition registration is setup-only and frozen before execution.
3. Payloads are validated before enqueue and persisted as canonical JSON-safe
   data, never pickle, callable objects, request objects, or process-local
   references.
4. A successful enqueue transaction makes the job durable before returning.
5. A claim and attempt increment occur atomically in the database.
6. Every renewal or settlement matches job ID, running state, owner, and the
   current lease token.
7. Expired work may run again; therefore execution is at least once, never
   exactly once.
8. A stale owner cannot overwrite the state or progress of a newer claim.
9. Retry count, backoff, priority, and queue concurrency are bounded.
10. Progress is advisory and cannot make a job succeeded, failed, or owned.
11. Job schema changes are checked-in migrations, not runtime DDL.
12. Normal routes and Chirp return types remain the application interface; the
    queue does not create a REST/JSON side channel.

## Typed payloads

The payload contract should follow the same authority direction as the
universal-operation RFC: Python type annotations and one shared constraint
vocabulary are authoritative. The implementation must not ask authors to keep
a dataclass, a JSON Schema document, and a database declaration synchronized.

An illustrative definition may eventually name one frozen/slotted dataclass or
an equivalent typed callable input. This RFC does not approve the decorator,
method, or import path.

The compiled definition needs at least:

- stable definition identity;
- payload type identity and explicit payload schema version;
- queue name;
- retry/backoff policy;
- priority bounds;
- queue concurrency policy; and
- a handler reference held only in the frozen runtime registry.

Only canonical JSON values cross the durability boundary: null, booleans,
finite numbers, strings, arrays, and objects with string keys. Encoding must
reject unsupported values before insertion. Decoding must validate the stored
version and constraints before invoking the handler.

Payload schema evolution cannot rely on importing an old Python class by
accident. A later implementation review must choose either explicit upcasters,
versioned handler identities, or a fail-loud compatibility policy. Unknown
definitions and undecodable payloads are deterministic failures, not transient
errors to retry forever.

## Persistent lifecycle

### Immutable and mutable facts

The physical schema is deferred, but its logical facts divide cleanly:

| Immutable after enqueue | Mutable under fenced transitions |
| --- | --- |
| job ID | state |
| definition identity | attempt count |
| payload document and version | available-at time |
| queue and priority | current owner and lease token |
| retry policy snapshot | lease expiry and heartbeat time |
| idempotency key | advisory progress and progress revision |
| creation time | bounded failure summary and terminal time |

Policy is snapshotted so a deploy does not silently change the retry budget or
priority of already-enqueued work. Handler code still evolves by deployment,
which is why payload-version compatibility remains explicit.

### State transitions

The first lifecycle has four states:

```text
enqueue                 claim
   |                       |
   v                       v
pending ----------------> running ----------------> succeeded
   ^                         |
   | retryable failure       | exhausted / non-retryable failure
   +-------------------------+---------------------> failed
                              \
                               +-- expired lease --> running (new claim/token)
```

Reclaiming expired work creates a new attempt and lease token. It need not pass
through an externally observable fifth state. There is no `cancelled` state in
the first slice.

`failed` is the initial dead-letter surface. The first implementation should
retain failed records for operator inspection rather than copying payloads to a
second queue. Replay, purge, archival, and retention policy require later
decisions.

### Atomic claim

The Postgres store should claim within one transaction:

1. select one eligible pending job, or one expired running job, for an eligible
   queue;
2. order deterministically by priority, availability time, creation time, and
   job ID;
3. lock the candidate with `FOR UPDATE SKIP LOCKED`;
4. reserve queue capacity in the same transaction;
5. set `running`, increment attempts, and assign owner, fresh lease token, and
   database-derived lease expiry; and
6. return the claimed snapshot and commit before invoking application code.

The final SQL and index plan need live-Postgres proof. The generic `Database`
transaction helper is a foundation; this RFC does not claim its current public
methods already form a queue store.

### Lease renewal and fencing

A heartbeat extends the lease only when job ID, state, owner, and token still
match. Completion, retry, terminal failure, and progress update use the same
predicate. Updating zero rows means ownership was lost and must surface as a
stale-claim result; it must not be treated as success.

Lease-token fencing protects the job record. It cannot undo external side
effects performed by a handler just before its lease expired. Handlers must use
idempotent operations, application transactions, or their own domain-level
fencing where duplicate effects matter.

Database time is authoritative for availability and lease expiry so instance
clock skew cannot create competing claims.

## Retry and backoff

Each job snapshots a positive maximum-attempt count and a bounded backoff
policy. A retryable failure before exhaustion returns the job to `pending`,
sets a future database-derived `available_at`, and clears lease ownership. A
failure at exhaustion moves the job to `failed`.

A crashed executor does not write a retry transition. Its `running` lease
expires and the next claimant increments the attempt. Crash recovery therefore
consumes attempt budget like any other invocation.

The first implementation should distinguish deterministic definition/payload
errors from transient handler failures so poison jobs do not consume repeated
leases. Exact exception classification and default backoff values are open
public-contract decisions.

Failure persistence must be bounded and public-safe. Raw tracebacks, exception
arguments, request bodies, credentials, or payload copies do not belong in the
job row by default.

## Idempotency

Idempotency is scoped to a queue. Concurrent enqueue operations with the same
non-null `(queue, idempotency_key)` must resolve to one retained job identity
using a database uniqueness guarantee, not a check-then-insert race.

The enqueue result should distinguish “created” from “existing” without
claiming that the handler's side effects are exactly once. A null key creates a
new job on every enqueue.

How long a completed or failed key remains reserved depends on retention and is
not decided here. Until expiration semantics are approved, implementations
must not silently recycle a key while its row remains retained.

## Priority and queue concurrency

Priority affects claim order within a queue; it is not a correctness guarantee
or a promise of strict wall-clock execution order. Exact numeric bounds,
defaults, and starvation mitigation remain open.

A queue concurrency limit is global to the shared Postgres store, not merely a
thread-pool size on one instance. Capacity must be reserved transactionally
with the claim. A plain `COUNT(running)` followed by an update is racy across
instances. The implementation review must select and prove a slot-row,
counter-row, or advisory-lock design and show that expired leases release
capacity without oversubscription.

Local executor concurrency may be lower than the queue limit. It must never be
presented as the distributed limit.

## Advisory progress

One candidate interoperability document, derived from Milo 0.4.1's field
shape, is:

```text
status: string
step: non-negative integer
total: non-negative integer
```

This RFC does not decide whether all three fields are required, what zero
means, or which relationships between `step` and `total` are valid. Whatever
schema is approved must keep updates JSON-safe, bounded, revisioned, and fenced
by the active lease token. Consumers may miss intermediate updates and should
treat the latest snapshot as authoritative.

Progress does not drive retries, completion, lease renewal, or cancellation.
An executor may renew a lease without changing progress, and a handler may
complete without ever reporting progress.

Future adapters can project the same semantic fields into Milo progress or an
application-owned SSE fragment. Chirp must continue to render HTML through
normal templates and return types; the store does not expose payload/progress
JSON directly to browsers or agents.

## Executor and lifecycle

The first executor is in-process with the application deployment. “In-process”
does not mean process memory is the source of truth: Postgres owns jobs,
claims, leases, capacity, and progress.

An executor needs explicit lifecycle ownership:

- start only after database connection, migration readiness, and app freeze;
- use bounded local concurrency;
- generate collision-resistant owner IDs and fresh tokens per claim;
- keep heartbeat work independent enough that a busy handler cannot starve it;
- stop claiming when readiness drops or shutdown begins;
- allow a bounded drain window for active attempts;
- stop renewing when drain expires, leaving work for lease-based recovery; and
- close without disconnecting the shared database out from under other app
  lifecycle users.

Python 3.14t removes the GIL bottleneck but does not make handler state safe.
The executor and handler registry need immutable snapshots, locks or queues for
shared mutable bookkeeping, deterministic shutdown tests, and ContextVar
isolation. A handler must not inherit an HTTP `Request`, session, or response
context from its enqueuing route.

Whether polling belongs to app lifespan, Pounce worker lifecycle, or a
dedicated executor component is unresolved. The answer must prevent duplicate
poller multiplication from accidentally exceeding configured local
concurrency.

## Contract checks

The issue requires broken definitions to fail before runtime. A future check
should consume a frozen job-definition snapshot and verify at least:

- every persisted/declared definition reference used by static enqueue wiring
  has a registered handler where static analysis can prove the identity;
- stable names, queue names, priorities, retry bounds, and concurrency limits
  are valid;
- payload types compile into the approved JSON-safe constraint vocabulary;
- duplicate definition identities fail during setup;
- a Postgres-backed job store has a reviewable migration declaration; and
- dynamic definition names are reported as analysis gaps, not guessed.

Static checks cannot inspect every row in a production queue or prove that a
handler is idempotent. Runtime store startup should fail clearly when required
tables or migration versions are absent; it must not repair them.

The category names, severity policy, compiler/snapshot fields, and migration
proof mechanism require a separate contracts check-in. This RFC does not add or
change any `app.check()` output.

## Security and data handling

Job payloads are durable application data. The first implementation must:

- use parameterized SQL for all payload and identity values;
- reject non-JSON-safe values before enqueue;
- avoid payloads, idempotency keys, progress text, and error details in normal
  logs or DevTools by default;
- expose no framework-owned list/get/retry HTTP endpoints;
- keep route authentication, authorization, validation, and CSRF behavior on
  the normal enqueueing route;
- require handlers to load and re-check current domain authority when a job's
  effect is security-sensitive; and
- bound persisted progress and failure text.

An enqueue-time user or tenant ID is a historical input, not proof that the
actor remains authorized when the job runs.

## Multi-instance behavior

Every application instance may poll the same queues. Postgres row locks,
queue-capacity reservations, leases, and fencing—not process-local locks—own
cross-instance correctness.

The first slice does not solve cross-instance SSE delivery. Issue #617 owns the
fan-out transport. A job may persist progress without automatically reaching a
browser connected to another instance.

Scheduled and periodic work belongs to #616. A future scheduler may enqueue
ordinary jobs, but it must not add time-trigger states to this lifecycle.

Milo Tasks alignment is downstream. Milo may use the durable primitive after
its task/cancellation contract is approved, but cancellation is not pulled into
the first job slice through that dependency.

## Rollout

### Phase 0: current RFC

- record existing data, migration, lifecycle, contract, and progress seams;
- define at-least-once state, lease, retry, idempotency, capacity, and progress
  invariants; and
- make no behavior change.

### Phase 1: private Postgres store

- approve exact provisional module, records, SQL migration, and defaults;
- implement enqueue, atomic claim, fenced renew/settle, retry, and progress;
- keep all names out of `chirp.__init__` and avoid AppConfig changes; and
- prove optional-domain isolation and live-Postgres concurrency.

### Phase 2: frozen definitions and contracts

- approve setup registration and enqueue shape;
- compile immutable definition snapshots at freeze;
- add explicitly reviewed contract category/severity behavior; and
- prove missing-handler and migration failures through `app.check()`.

### Phase 3: in-process executor

- approve lifecycle ownership and bounded local concurrency;
- run typed handlers with heartbeat and graceful drain;
- prove free-threaded and multi-instance recovery; and
- provide operational metrics without payload leakage.

### Phase 4: product proof and guidance

- dogfood one real background workload;
- expose progress through an application-owned SSE surface;
- kill a worker mid-attempt and prove reclaim plus completion; and
- benchmark claim throughput and publish honest graduation guidance before
  recommending the store beyond measured bounds.

SQLite parity, schedules, cross-instance live fan-out, MCP Task cancellation,
and any public stable API remain separate work.

## Required proof before shipping

1. Two concurrent claimers cannot receive the same unexpired attempt.
2. An expired claim is reclaimed with a new owner/token and attempt number.
3. A stale owner cannot renew, update progress, succeed, retry, or fail the
   newly claimed job.
4. Kill-after-side-effect proof documents at-least-once duplication risk rather
   than claiming exactly once.
5. Retryable failures honor attempt bounds and database-clock backoff.
6. Exhausted and deterministic failures enter the terminal failed set.
7. Concurrent queue-scoped idempotent enqueues return one retained identity.
8. Null idempotency keys always create distinct jobs.
9. Priority ordering is deterministic and queue capacity cannot be exceeded by
   multiple instances.
10. Progress is fenced, bounded, JSON-safe, monotonic by revision, and does not
    alter lifecycle state.
11. Payload validation rejects arbitrary objects and schema-version mismatch
    before handler invocation.
12. Missing handlers and missing migrations fail with actionable diagnostics
    after their contract behavior is separately approved.
13. Imports and HTML-only apps do not connect to Postgres or create job state.
14. Python 3.14t stress tests cover claim bookkeeping, handler concurrency,
    ContextVar isolation, heartbeat, and shutdown.
15. Checked-in migrations are deterministic and no runtime path issues DDL.
16. Logs, errors, progress adapters, and inspection omit payloads and secrets by
    default.

## Rejected alternatives

### Exactly-once execution

Rejected. Lease recovery permits overlapping handler execution around expiry,
and a database cannot atomically roll back arbitrary external side effects.

### Pickle or arbitrary Python objects

Rejected. They are unsafe across trust boundaries, bind durable rows to code
layout, and make schema evolution unverifiable.

### In-memory queue with database checkpointing

Rejected. A successful enqueue must already be durable, and every instance must
coordinate through one authority.

### Automatic table creation

Rejected. Runtime DDL bypasses reviewable migrations and can race across
instances or hide an incomplete deployment.

### Redis/Celery as the first backend

Rejected for the first slice. The approved product proof is app plus Postgres.
Graduation guidance may recommend other infrastructure after measured limits.

### SQLite semantic parity in the first slice

Rejected. `SKIP LOCKED`, lease/concurrency behavior, and multi-instance claims
need a Postgres-first proof before a second backend can claim the same contract.

### One table as a workflow engine

Rejected. There are no DAGs, child workflows, compensation, scheduler,
cancellation state, arbitrary result documents, or workflow JSON API.

## Open questions requiring maintainer check-in

These decisions touch Stop And Ask surfaces and are not approved by this RFC:

1. What provisional module, registration form, enqueue form, and import path
   express definitions without creating a stable top-level API?
2. What exact SQL tables, column types, indexes, migration ownership, and schema
   version identify the first Postgres store?
3. What are the defaults and allowed bounds for attempts, backoff, priority,
   lease duration, heartbeat interval, payload/progress size, polling, drain,
   and queue concurrency?
4. Does queue capacity use slot rows, a locked counter row, or an advisory-lock
   protocol, and how is capacity recovered after expiry?
5. Does executor ownership attach to app lifespan, Pounce worker lifecycle, or
   a separate component?
6. What payload constraint compiler and version/upcast policy are authoritative?
7. Which failures are non-retryable, and what bounded failure metadata is safe
   to persist by default?
8. How long do succeeded/failed jobs and idempotency keys remain retained, and
   who owns purge or manual replay?
9. What future `app.check()` categories, subjects, severity, and migration
   evidence make missing definitions/tables actionable without scanning live
   production rows?
10. Is `status`/`step`/`total` the complete first progress schema, and how is
    compatibility with future Milo Progress versions reviewed without making
    durable-job semantics depend on a particular Milo revision?

## Non-goals

- public stable job types or top-level exports;
- AppConfig job fields;
- automatic schema mutation;
- SQLite or generic backend protocols in the first slice;
- exactly-once execution;
- Redis, Celery, Kafka, or a separate worker fleet requirement;
- scheduling or cron;
- cancellation;
- DAG/workflow orchestration, compensation, or sagas;
- arbitrary Python serialization;
- durable arbitrary handler return values;
- job-admin, workflow JSON, or payload/progress endpoints;
- replacing normal route auth, validation, return types, templates, or SSE;
- solving cross-instance SSE fan-out; or
- claiming a throughput ceiling before measurement.

## Collateral

No changelog, public API, site, example, scaffold, CLI, migration, benchmark, or
deployment collateral moves for this proposed RFC.

An implementation would require, at minimum, a reviewed SQL migration, optional
data documentation, public/provisional API status, contract category docs,
live-Postgres and free-threaded tests, one product-shaped example, operational
metrics and security guidance, a towncrier fragment, and measured graduation
guidance. SQLite documentation must not imply parity until parity exists.

[issue-615-decision]: https://github.com/lbliii/chirp/issues/615#issuecomment-4929195371

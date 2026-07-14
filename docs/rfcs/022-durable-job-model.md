# RFC 022: Durable job model

**Status:** Accepted — Phase 1 implemented; Phase 2/3 boundaries approved

**Issue:** [#615](https://github.com/lbliii/chirp/issues/615)

**Decision:** [#719](https://github.com/lbliii/chirp/issues/719)

**Parent saga:** [#614](https://github.com/lbliii/chirp/issues/614)

**Last audited:** 2026-07-14

**Shipping impact:** Private data surface plus an approved decision record.
Issue #677 adds a private Postgres store, three internal tables through a
package-shipped migration, and live database proof. Issue #719 freezes the
provisional definition, contract, lifecycle, progress, and backend boundaries
for later implementation. Neither issue adds a public API, runtime executor,
AppConfig field, CLI command, contract finding, scheduler, cancellation
protocol, or non-Postgres backend.

## Summary

Chirp's Phase 1 proof provides a small private Postgres-backed durable store
for work that must survive process restart and be claimed safely across
instances. Later phases add definitions and an executor. The intended product
is a job store and executor, not a workflow engine.

The accepted model provides:

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

Phase 1 records its private Python names, module placement, SQL schema, and
bounded store defaults below. The #719 decision records the minimum provisional
definition, contract, lifecycle, and compatibility semantics that Phase 2 and
Phase 3 may implement. Exact Python names and public promotion remain separate
implementation and graduation reviews.

## Current implementation audit

This section describes the Phase 1 implementation from issue #677 against
`main` at `d0cfba96`.

### Private Phase 1 store, no executor

`src/chirp/data/_jobs.py` now contains the private `PostgresJobStore` proof.
It can validate the reviewed schema, enqueue JSON-safe snapshots, claim with
`FOR UPDATE SKIP LOCKED`, renew leases, update fenced progress, and settle
success, retry, or terminal failure. It is intentionally absent from both
`chirp.__all__` and `chirp.data.__all__`.

There is still no public job definition, handler registry, claim loop,
executor, or durable-job contract rule. `App.render()` remains only a
rendering helper; it does not persist, claim, retry, lease, or execute work.

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

The durable-job schema uses this migration surface through
`src/chirp/data/migrations/jobs/001_durable_jobs.sql`. The store constructor
and runtime methods issue no DDL; missing schema version 1 fails with the exact
migration path and `chirp migrate` guidance.

### Phase 1 implementation decisions

- `_chirp_job_schema` carries the exact private schema version;
  `_chirp_job_queues` owns persisted queue capacity; `_chirp_jobs` stores the
  immutable request snapshot and fenced mutable lifecycle.
- A locked queue row serializes capacity decisions. Each claim reconciles its
  counter from unexpired running rows before selecting one candidate with
  `FOR UPDATE SKIP LOCKED`; expired leases therefore release capacity without
  cross-instance oversubscription.
- Job IDs and lease tokens are UUIDs. Definition, queue, owner, idempotency,
  progress, payload, failure, attempts, priority, delay, lease, backoff, and
  capacity inputs are bounded before SQL. Payloads are canonical JSON-safe
  values with a 64 KiB encoded limit.
- Default private policy is a 30-second lease, queue capacity 1, priority 0,
  three attempts, one-second exponential backoff, and a 300-second backoff
  cap. These are Phase 1 implementation values, not approved public API
  defaults.
- Advisory progress is the bounded `status` / `step` / `total` document and a
  monotonically increasing revision. It never changes lifecycle state.
- Store SQL bypasses the generic database echo path while retaining the same
  pool and transaction boundaries. Database failures use a fixed redacted
  message so payloads, keys, progress, and failure values are not logged or
  copied into framework errors.

### Lifecycle and free-threading boundary

`src/chirp/app/lifecycle.py` connects the configured database during lifespan
startup, runs setup hooks, flips readiness only after startup succeeds, then
drains shutdown hooks before disconnecting the database. Separate worker
startup and shutdown hooks are registered during setup and invoked by Pounce
worker lifecycle messages.

Those hooks are possible executor seams, but #719 assigns executor ownership to
the application lifespan. One app instance may start exactly one executor after
database readiness and app freeze. Pounce worker hooks must not start a second
poller for that app instance. Each deployment process may host its own app
instance and executor; PostgreSQL, not process-local bookkeeping, still owns
global queue capacity. Phase 3 must prove that ownership under Python 3.14t.

### Contract/compiler boundary

`ContractCheckSnapshot` is a frozen read model populated after app setup. It
contains registries and compiler facts required by current checks, but no job
definitions. `app.check()` therefore cannot currently verify a job handler,
payload type, queue, retry policy, or migration.

The provisional job-definition registry belongs to setup/freeze. Runtime
enqueue must reference a frozen definition by stable identity; it must not
register handlers after freeze. Phase 2 may add the approved frozen snapshot
and provisional `jobs` category described below, but exact Python names and any
stable promotion still require implementation review.

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

## Approved Phase 2 and Phase 3 boundaries

Issue #719 approves semantic shapes rather than stable Python spellings. Phase
2 and Phase 3 remain provisional until the product proof and graduation review
in Phase 4. In particular, no top-level export or `AppConfig` field is approved.

### Definition, registration, and enqueue

A provisional definition is a frozen, slotted setup-time value containing:

- a stable definition identity;
- one authoritative typed payload contract and explicit schema version;
- queue, priority, retry/backoff, and queue-concurrency policy;
- one asynchronous handler reference held only in the frozen registry; and
- the bounds needed to compile and validate those values before runtime.

Registration occurs only during setup. App freeze publishes one immutable
registry snapshot for contract checks, enqueue validation, and executor reads.
Duplicate identities fail setup, post-freeze mutation fails loud, and concurrent
reads require no mutable shared registry state.

Enqueue accepts a registered definition identity and a value validated against
that definition's payload contract. It snapshots canonical JSON, the explicit
payload schema version, and execution policy into the existing Postgres store.
It does not accept arbitrary objects, unregistered dynamic handlers, or a second
hand-maintained schema document.

Payload compatibility is exact and fail-loud for this epic. Unknown definition
identities, unsupported stored schema versions, and malformed decoded payloads
are deterministic non-retryable failures. Upcasters and implicit imports of old
Python classes are not approved. A future RFC may add an explicit evolution
mechanism without changing existing durable rows by accident.

### Failure, retention, and progress

Handler failures use the retry policy snapshotted on the job. Definition lookup,
schema-version, payload-decoding, and framework validation failures do not
retry. Persisted failure metadata is limited to a stable safe code and bounded,
redacted summary; raw tracebacks, exception arguments, payloads, credentials,
and request state remain excluded.

Succeeded and failed rows, including non-null idempotency keys, remain retained
for this epic. It does not add purge, replay, archival, retention scheduling, or
automatic idempotency-key recycling. Those operations need a later policy and
operator-surface review.

The provisional progress document retains the Phase 1 shape:

```text
status: required bounded string
step: non-negative integer, default 0
total: non-negative integer, default 0
```

`total == 0` means the total is unknown. When `total > 0`, `step` must not exceed
`total`. This remains advisory, replaceable, revisioned, and lease-fenced. It is
not coupled to a Milo package version and does not drive lifecycle transitions.

### Executor ownership and free-threading

The application lifespan owns exactly one executor per app instance. It starts
only after database connection, migration readiness, setup, and app freeze.
Pounce lifecycle hooks must not multiply pollers for the same instance. Local
concurrency is bounded independently from the database-coordinated global queue
limit.

Shutdown stops new claims, drains active handlers for a bounded interval, and
then stops renewal so unfinished work becomes reclaimable by lease expiry. The
executor does not disconnect the shared database. Registry state stays frozen;
mutable claim, heartbeat, and shutdown bookkeeping uses explicit async
coordination rather than relying on the GIL. Handler tasks begin with isolated
`ContextVar` state and never inherit an HTTP request, session, or response.

### Contract and migration policy

Phase 2 may add a provisional `jobs` contract category with these defaults:

- **error:** duplicate or malformed definitions, missing statically referenced
  handlers, invalid payload contracts or policy bounds, and a configured
  Postgres job store without the checked-in migration declaration;
- **warning:** a dynamic definition reference that static analysis cannot prove;
  and
- **runtime startup error:** missing or incompatible live database tables or
  schema version.

`app.check()` inspects frozen declarations and compiler facts. It does not scan
production queue rows, connect solely to inspect a live schema, guess dynamic
identities, or claim that a handler is idempotent.

Durable-job schema ownership remains with deterministic, package-shipped,
reviewable migrations applied through Chirp's existing migration workflow. The
store, registry, contracts, and executor never issue DDL or repair a deployment.

### Backend boundary

SQLite parity is rejected for epic #615, not merely deferred within its phases.
SQLite lacks the proven `SKIP LOCKED`, lease, and multi-instance concurrency
semantics that define this Postgres-backed contract. A later RFC may consider a
dev-only or single-box SQLite adapter, but it must document weaker semantics and
must not claim parity with this backend.

### Decision matrix and proof ownership

| Concern | Approved boundary | Required implementation proof | Owner and collateral |
| --- | --- | --- | --- |
| Crash recovery | At-least-once reclaim consumes an attempt and receives a new owner/token. | Kill an executor after claim and after an external side effect; prove reclaim, stale-owner fencing, completion, and the documented duplicate-effect risk. | Phase 3 native child; executor operations guidance and safe metrics. |
| Idempotency | The existing queue-scoped key and retained-row semantics remain authoritative; no automatic recycling. | Concurrent equal keys retain one identity; null keys remain distinct; terminal rows keep their key. | #720 for validated enqueue wiring; existing live-Postgres store tests remain the persistence proof. |
| Retries | Deterministic definition/payload failures do not retry; handler failures use snapshotted policy. | Exhaustion, database-clock backoff, malformed stored versions, redacted failure metadata, and crash-consumed attempts. | #720 for definition/payload classification; Phase 3 child for handler execution. |
| Malformed definitions | Setup/freeze rejects duplicates, invalid identities, payload contracts, and policy bounds. | Fail-loud setup and `app.check()` cases, mounted composition, post-freeze mutation rejection, and actionable subjects. | #720; provisional API inventory, contract documentation, focused example, and changelog for implemented behavior. |
| Lifecycle and free-threading | One app-lifespan executor per app instance; frozen registry and explicit async coordination. | Python 3.14t stress for concurrent reads, claims, heartbeat isolation, ContextVar isolation, bounded drain, and deterministic shutdown. | Phase 3 native child; lifecycle and operations documentation. |
| Optional dependencies | Job imports and HTML-only apps neither connect to PostgreSQL nor create job state. | Import isolation, app startup without job configuration, and missing-domain failure only when job behavior is requested. | #720 and Phase 3 child; explicit no-impact result for core HTML docs/examples. |
| SQLite gaps | No SQLite parity in #615; a later adapter must admit weaker semantics. | No SQLite implementation or parity claim is required to graduate this epic. Any future adapter begins with a separate RFC and semantic-gap tests. | Parent #615 scope reconciliation; no current public collateral. |
| Migration ownership | Package-shipped reviewed SQL through the existing migration workflow; no runtime DDL. | Deterministic migration, declaration diagnostics, missing/incompatible live-schema startup failure, and a scan proving runtime paths issue no DDL. | Existing Phase 1 migration plus #720 contract proof; migration and operations docs move only with implementation. |

The decision record itself changes no runtime behavior. Acceptance #719 is
therefore `n/a (decision-only RFC and parent-scope reconciliation)`; behavioral
traceability belongs to the implementation children named in the matrix.

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

A provisional definition names one frozen/slotted dataclass or equivalent typed
callable input. The exact decorator, method, module, and import path remain for
the Phase 2 implementation review; #719 approves no stable spelling.

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
accident. This epic uses exact stored schema-version compatibility and fails
loud on a mismatch. Unknown definitions and undecodable payloads are
deterministic failures, not transient errors to retry forever. Upcasters remain
future RFC work.

## Persistent lifecycle

### Immutable and mutable facts

The Phase 1 physical schema follows this logical split:

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

`failed` is the initial dead-letter surface. This epic retains failed records
for operator inspection rather than copying payloads to a second queue. Replay,
purge, archival, retention policy, and automatic idempotency-key recycling are
not part of the epic.

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

Deterministic definition lookup, schema-version, payload-decoding, and framework
validation failures enter `failed` without retry. Handler failures follow the
retry policy snapshotted at enqueue until attempts are exhausted. Exact public
exception types and provisional policy spellings remain Phase 2 implementation
details.

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

`status` is required and bounded; `step` and `total` default to zero and remain
non-negative. Zero `total` means unknown. When `total` is positive, `step` must
not exceed it. Updates stay JSON-safe, bounded, revisioned, and fenced by the
active lease token. Consumers may miss intermediate updates and should treat
the latest snapshot as authoritative.

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

Polling belongs to the app lifespan, with exactly one executor per app instance.
Pounce worker hooks must not start an additional poller for that instance.
Separate app instances may each poll because PostgreSQL owns cross-instance
claims and global queue capacity.

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

Phase 2 may implement the provisional `jobs` category and severity policy
approved above. The compiler/snapshot field names and diagnostic wording remain
implementation-review details. This RFC itself does not add or change any
`app.check()` output.

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

### Phase 0: RFC — complete

- record existing data, migration, lifecycle, contract, and progress seams;
- define at-least-once state, lease, retry, idempotency, capacity, and progress
  invariants; and
- make no behavior change.

### Phase 1: private Postgres store — complete in #677

- approve exact provisional module, records, SQL migration, and defaults;
- implement enqueue, atomic claim, fenced renew/settle, retry, and progress;
- keep all names out of `chirp.__init__` and avoid AppConfig changes; and
- prove optional-domain isolation and live-Postgres concurrency.

### Phase 2: frozen definitions and contracts

- implement the approved provisional setup registration and enqueue semantics;
- compile immutable definition snapshots at freeze;
- add the approved provisional `jobs` category/severity behavior; and
- prove missing-handler and migration failures through `app.check()`.

### Phase 3: in-process executor

- implement one app-lifespan executor per app instance with bounded local
  concurrency;
- run typed handlers with heartbeat and graceful drain;
- prove free-threaded and multi-instance recovery; and
- provide operational metrics without payload leakage.

### Phase 4: product proof and guidance

- dogfood one real background workload;
- expose progress through an application-owned SSE surface;
- kill a worker mid-attempt and prove reclaim plus completion; and
- benchmark claim throughput and publish honest graduation guidance before
  recommending the store beyond measured bounds.

SQLite parity is outside epic #615. Schedules, cross-instance live fan-out, MCP
Task cancellation, retention/replay, and any public stable API remain separate
work.

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

### SQLite semantic parity in epic #615

Rejected. `SKIP LOCKED`, lease/concurrency behavior, and multi-instance claims
define the Postgres-backed contract and do not have proven equivalent SQLite
semantics. A later RFC may consider a weaker dev-only or single-box adapter, but
it must not claim parity.

### One table as a workflow engine

Rejected. There are no DAGs, child workflows, compensation, scheduler,
cancellation state, arbitrary result documents, or workflow JSON API.

## Deferred decisions requiring later maintainer check-in

Issue #719 deliberately leaves these Stop And Ask surfaces unresolved:

1. Exact provisional Python names, decorator or method spellings, and module
   placement for Phase 2.
2. Exact public exception types, retry-policy spelling, and executor tuning
   defaults for their implementation reviews.
3. Retention duration, purge, replay, archival, and idempotency-key expiration.
4. Upcasters or another payload-evolution mechanism beyond exact version
   compatibility.
5. Stable promotion, top-level exports, AppConfig integration, and compatibility
   tier after Phase 4 product proof.
6. Any SQLite adapter, which requires its own RFC and an explicit weaker-semantics
   contract.

## Non-goals

- public stable job types or top-level exports;
- AppConfig job fields;
- automatic schema mutation;
- SQLite or generic backend protocols in epic #615;
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

## Phase 1 collateral

Issue #677 ships the reviewed SQL migration, explicit internal API status,
towncrier fragment, and live-Postgres/free-threaded tests. The PostgreSQL matrix
and Python 3.14t gate both exercise the store. No site example, scaffold, CLI,
contract category, benchmark claim, executor guidance, or generated site output
moves because Phase 1 is private and does not execute handlers. SQLite
documentation continues to make no durable-job parity claim.

## Decision collateral

Issue #719 updates only this RFC and the live #615 parent scope. It adds no
runtime behavior, public API, contract finding, example, scaffold, benchmark,
generated site output, or changelog fragment. Phase 2 issue #720 owns the
provisional definitions and contract collateral. A separate native Phase 3
child must own executor implementation and lifecycle proof before that work
begins.

[issue-615-decision]: https://github.com/lbliii/chirp/issues/615#issuecomment-4929195371

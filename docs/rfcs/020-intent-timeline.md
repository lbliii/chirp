# RFC 020: Intent Timeline

**Status:** Accepted; private capture foundation implemented by #647 and
private artifact/comparator implemented by #648

**Issue:** [#336](https://github.com/lbliii/chirp/issues/336)

**Parent saga:** [#335](https://github.com/lbliii/chirp/issues/335)

**Last audited:** 2026-07-09

**Shipping impact:** Private debug/test capture only. This RFC does not add an `AppConfig` field,
public type, CLI command, middleware, route, replay endpoint, DevTools control,
or production capture behavior.

## Summary

Chirp should make an ordered history of typed hypermedia observations useful
for debugging and regression proof. The history records the decisions Chirp
already owns—route identity, request mode, return type, template/block target,
render intent, status, compiled transition identity, and SSE lifecycle—without
recording rendered HTML or application context values.

The design has a strict two-level boundary:

1. **Observation replay** reads a versioned, immutable sequence of redacted
   facts and lets DevTools or tests inspect, filter, compare, and assert them.
   It performs no request and no application mutation.
2. **Execution replay** is an application-owned test operation. A checked-in
   fixture driver establishes database/session state and maps safe step names
   to explicit TestClient or browser actions. Chirp compares the new typed
   observations with the fixture; it never reconstructs a request from a
   production trace or silently repeats a mutation.

This distinction is necessary. A response intent is deterministic evidence of
the rendering decision that occurred, but it is not a complete record of the
request inputs, database snapshot, clock, random source, external services, or
side effects that produced it.

The first implementation should remain debug/test-only, bounded, and
observation-only. Production or staging capture belongs to sibling issue #345
and requires a separate privacy, retention, and operational review.

## Current foundations

### Typed return observations

`src/chirp/templating/trace.py` defines the frozen, slotted `ReturnTrace` used
by debug response headers and server traces. It already carries bounded:

- return type and category;
- method and request mode;
- render intent, status, template, block, target, and swap;
- context **key names**, never context values;
- stable route and observation identities; and
- compiled transition identities and public-safe descriptions.

`src/chirp/server/transition_trace.py` correlates a return observation with the
frozen internal `HypermediaProgram`. Dynamic route parameter values are not
part of the stable route identity. `tests/test_transition_trace.py` proves that
`/items/sensitive-route-value-42` is exported as `/items/{item_id}` and that the
private value is absent from the serialized trace.

The trace is diagnostic metadata. It does not replace the HTML response or
create a JSON application side channel.

### Bounded server trace store

`src/chirp/server/debug_runtime.py` creates a `DebugTraceStore` only when
`debug=True`. The store:

- uses a lock around publication;
- retains at most 500 records in a `deque`;
- records HTTP response observations and SSE lifecycle phases;
- filters framework-internal records by default; and
- exposes a JSON debug endpoint through the existing internal wiring.

The store is process-local and app-wide. It mixes observations from different
browsers, has timestamps but no authoritative total-order sequence, and is not
a session recorder or durable log.

Issue #647 replaces the store's mutable retained mappings with the private
frozen/slotted records in `src/chirp/server/intent_timeline.py`. The debug-only
adapter now publishes an authoritative sequence under one lock, copies only
allowlisted structural facts from `ReturnTrace` and SSE lifecycle metadata,
derives opaque capture correlation IDs instead of retaining caller-supplied
request IDs, links SSE children to their typed response, and exposes explicit
count/byte truncation state. It still remains one process-local app capture; browser
scoping, artifacts, comparison, and additional transport correlation belong to
#648–#650.

### Versioned private artifact and comparator

Issue #648 implements the private observation-only artifact in
`src/chirp/server/intent_replay.py`. The `.chirp-replay` envelope is exact and
versioned as `chirp.intent-timeline/1`; it accepts only `kind="observation"`
with `public-safe-v1` redaction. It contains created-with Chirp version,
optional program fingerprint, explicit truncation metadata, and typed request,
render-intent, response, SSE, or diagnostic events.

The loader accepts at most 1 MiB and 500 events, requires unique contiguous
sequence values and valid earlier parent links, and rejects unknown versions,
kinds, channels, detail variants, missing/extra fields, non-finite numbers,
absolute template paths, query-bearing route patterns, and forbidden
body/HTML/header/cookie/session/auth/context/data fields. Errors name the
artifact and JSON field path without echoing a rejected value. Absolute wall
clock is not persisted.

The private semantic comparator treats route/mode, return/render intent,
block/target, status, compiled transitions, lifecycle facts, causal parent,
ordering, truncation, and program fingerprint as authoritative. It normalizes
only elapsed time, opaque capture request IDs, per-event absolute sequence
values, capture source, and Chirp patch-version differences. Loading and comparison
perform no imports, requests, route calls, DOM writes, or application mutation.
No CLI, public testing type, top-level export, production ingestion, or
artifact compatibility promise is added.

### Browser DevTools history

`src/chirp/server/devtools/js/state.js` maintains bounded browser-side arrays
for htmx records, errors, history events, SSE connections/events, transition
traces, and View Transition events. Only DevTools preferences are persisted to
`localStorage`; activity records are not.

`src/chirp/server/devtools/js/errors.js` and
`src/chirp/server/devtools/js/ui.js` already export those arrays as JSON. That
export is useful diagnostic evidence, but it is not a versioned replay schema:
it has no artifact compatibility contract, application fingerprint, global
sequence, fixture driver, or assertion policy.

### Test transition evidence

`src/chirp/testing/transitions.py` parses typed observations and reports
observed request modes and unexercised compiled transitions. This is the right
assertion seam for a future replay fixture. It does not currently load a
timeline artifact or execute requests.

### SSE recovery remains application-owned

`docs/rfcs/007-sse-last-event-id-recovery.md` deliberately rejects a framework
event replay buffer. Intent Timeline diagnostics do not change that decision.
Recording that an SSE event or lifecycle transition was observed cannot be
used to resend business events to a browser after reconnect.

## Problem statement

The current pieces answer local questions—what one response returned, which
compiled edge it matched, or which events DevTools recently saw—but they do not
form one replayable contract:

- server records from multiple clients are not causally scoped;
- browser and server arrays have independent ordering;
- wall-clock milliseconds cannot resolve concurrent publication order;
- Stream and Suspense lifecycle evidence is incomplete relative to HTTP/SSE;
- exports have no schema version or compatibility policy;
- no artifact distinguishes redacted observations from executable inputs;
- no reset boundary makes repeating a mutation safe; and
- no comparator explains a replay divergence in Chirp terms.

A DOM snapshot would appear to fill some gaps, but it would record the result
of browser mutation rather than the server intent. It would also capture user
content and would not prove that the named-block/render-plan contract was
followed.

## Decision

Adopt a future **Intent Timeline** as an ordered, immutable sequence of
public-safe observations. Keep capture, storage, and execution intentionally
separate.

| Layer | Owns | Must not own |
| --- | --- | --- |
| Return tracing | One bounded typed response observation | Raw context, HTML, request body |
| Timeline assembly | Ordering and causal grouping of observations | Business-state reconstruction |
| Replay artifact | Versioned redacted facts and expectations | Secrets, cookies, session values |
| Fixture driver | Explicit setup and safe test actions | Generic production traffic replay |
| Comparator | Semantic divergence report | DOM-diff-as-authority |
| DevTools | Browse/export observation history | Mutation or production time travel |

The timeline remains a projection of the existing render/transition authority.
It must not create a parallel return type, template renderer, route graph, or
serialization path for application data.

## Terminology

- **observation** — one bounded fact emitted at a Chirp-owned boundary;
- **timeline** — observations in one explicit scope with a total sequence;
- **capture** — publication of observations into a bounded debug/test sink;
- **artifact** — an immutable versioned export of a timeline;
- **observation replay** — load and inspect an artifact without executing code;
- **fixture driver** — application test code that establishes state and invokes
  explicitly named actions;
- **execution replay** — run a fixture driver and compare new observations;
- **fork** — start a new test scenario from an explicitly prepared checkpoint,
  never from hidden server view state.

“Replay” without one of the two qualified meanings above is too ambiguous for
public documentation or APIs.

## Proposed observation model

The illustrative internal shape is frozen and slotted, but this RFC does not
approve a public Python type:

```python
@dataclass(frozen=True, slots=True)
class TimelineObservation:
    sequence: int
    elapsed_us: int
    channel: Literal["http", "stream", "suspense", "sse", "browser"]
    phase: str
    request_id: str | None
    parent_sequence: int | None
    route_id: str | None
    route_pattern: str | None
    request_mode: str | None
    return_type: str | None
    render_intent: str | None
    status: int | None
    template: str | None
    block: str | None
    target: str | None
    transition_ids: tuple[str, ...]
    notes: tuple[str, ...]
```

Fields are copied from already-redacted typed traces or produced at a narrow
transport lifecycle boundary. The artifact never serializes arbitrary
metadata mappings supplied by applications.

### Identity

`sequence` is the authoritative order inside one timeline. It is allocated
while holding the publication lock and never inferred from timestamp order.
`elapsed_us` is relative to capture start and is diagnostic only.

`request_id` correlates phases during one capture but is not expected to match
on a later execution. Stable comparison uses route, observation shape, and
compiled transition identities. `parent_sequence` links a deferred chunk or
SSE lifecycle record to the observation that opened its work.

### Scope

The first implementation uses an explicit debug/test capture scope. It does
not infer identity from a session cookie and does not set a new cookie.

For a browser capture, the browser owns an opaque, unprivileged capture token
and sends it only to debug-owned endpoints/headers. The server accepts it only
when debug wiring is enabled. A token separates concurrent diagnostic streams;
it is not authentication, authorization, or application session state.

The exact header/endpoint shape is deferred because it changes debug protocol
behavior and requires a separate review. Until then, the existing app-wide
store must not be described as a per-session timeline.

### Event classes

The minimum useful timeline includes:

1. request start and matched route pattern;
2. final typed response observation;
3. htmx/browser settle outcome for targeted requests;
4. each OOB block identity selected for delivery;
5. Stream open, chunk count/identity where available, completion, and failure;
6. Suspense shell, deferred block completion order, failure/fallback, and close;
7. SSE connect, open, named event metadata, error, reconnect, and close; and
8. View Transition/history events needed to explain browser navigation.

Payload bodies, rendered chunks, SSE `data`, and DOM snapshots are excluded.
For an event whose value matters to a regression, the application fixture owns
a safe domain assertion outside the generic timeline.

## Artifact format

The proposed extension is `.chirp-replay`, containing UTF-8 JSON. The extension
does not imply that arbitrary captured traffic is executable.

An illustrative observation artifact is:

```json
{
  "schema": "chirp.intent-timeline/1",
  "kind": "observation",
  "created_with": {"chirp": "0.x"},
  "application": {
    "program_fingerprint": "sha256:...",
    "fixture": null
  },
  "capture": {
    "source": "debug-browser",
    "redaction": "public-safe-v1",
    "truncated": false
  },
  "events": []
}
```

The fingerprint is derived from stable internal program identities, not file
paths, source text, object identity, database data, or registration order. It
warns that the application contract changed; it does not expose the private
`HypermediaProgram` or make its dataclasses public.

An executable checked-in artifact additionally names an application-owned
fixture driver and ordered safe step IDs:

```json
{
  "schema": "chirp.intent-timeline/1",
  "kind": "fixture",
  "application": {
    "program_fingerprint": "sha256:...",
    "fixture": "tests.replays.lucky_cat:archive_flow"
  },
  "steps": [
    {"id": "open-inbox", "expect": ["observation:..."]},
    {"id": "archive-first", "expect": ["observation:..."]}
  ],
  "events": []
}
```

The import string is illustrative and is not an approved CLI or public API.
The driver, not the artifact loader, maps `archive-first` to concrete request
inputs and owns setup/cleanup.

### Compatibility

- Unknown schema majors fail with an actionable error.
- Unknown event channels/phases in the same major remain visible but are not
  silently treated as satisfied expectations.
- Extra fields are preserved only by tools that explicitly support them; the
  canonical loader does not accept arbitrary application data.
- A mismatched program fingerprint is a named divergence, not an automatic
  fixture rewrite.
- Truncated capture is explicit and cannot claim complete transition coverage.

## Redaction and privacy model

The base `public-safe-v1` profile permits structural facts only:

- route patterns, never dynamic path parameter values;
- method, response status, and request mode;
- logical template/block/target names;
- typed return and render intent;
- stable compiled identities and bounded descriptions;
- content type class, byte counts, timing, and lifecycle phases where useful;
- framework/package versions needed to interpret the artifact.

It excludes:

- query strings and concrete URLs;
- request/response bodies and rendered HTML;
- form, JSON, upload, and SSE payload data;
- cookies, session IDs, CSRF values, auth headers, and user identity;
- context values and, by default, context key names;
- exception locals, database values, and arbitrary application notes;
- absolute paths, source text, environment variables, and DSNs.

Names are not automatically harmless. An application may put a tenant or user
identifier in a target, route name, or event name. The exporter therefore runs
a deny-pattern/public-safe scan and supports an application-owned allowlist
only through a separately reviewed extension. A failing scan blocks export; it
does not replace suspected values with a misleading hash and continue.

The first implementation is debug/test-only. Enabling bounded production or
staging capture, retention, sampling, access control, deletion, or upload is
out of scope and belongs to #345.

## Observation replay

Loading an observation artifact may:

- validate schema, bounds, ordering, and parent links;
- filter by route, request mode, return type, block, or transition;
- render a DevTools scrubber and causal tree;
- compare two artifacts semantically;
- report missing, added, reordered, or changed observations; and
- build transition coverage from recorded stable IDs.

It must not import the application, open a network connection, invoke a route,
write a database, or mutate the browser DOM. Observation replay is safe to use
in an issue report because it is data inspection, not traffic replay.

## Execution replay

Execution replay requires all of the following:

1. a checked-in fixture artifact, not an unreviewed production export;
2. an explicit fixture driver import approved by the test suite;
3. deterministic setup of database, clock, random source, and external seams
   relevant to the scenario;
4. a fresh TestClient/app lifecycle or isolated browser context;
5. one named driver action per step;
6. explicit permission in the driver for every mutation;
7. rollback or teardown after failure; and
8. comparison against typed observations and application-owned assertions.

Chirp must never infer “safe to repeat” from HTTP method alone. GET handlers can
have side effects, while a well-designed POST fixture can be safely isolated.
The driver is the authority.

A fork starts from a named driver checkpoint. It cannot clone a live user
session, copy an application database implicitly, or continue from a response
context hash. “What if they clicked Archive?” becomes a new fixture branch
whose setup and mutation are visible in test code.

## Comparison policy

The comparator groups differences by semantic identity rather than raw JSON
position:

- route/request mode changed;
- return type or render intent changed;
- expected named block/target disappeared;
- OOB/Suspense/SSE order changed;
- compiled transition became unobserved;
- status or lifecycle completion changed;
- capture truncated before an expectation could be evaluated; or
- application fingerprint no longer matches.

Wall time, generated request IDs, timestamps, and package patch versions are
informational by default. Tests may opt into bounded timing assertions only
when the fixture controls the clock or uses a documented benchmark method.

An empty target, missing non-optional OOB block, or full document in a narrow
fragment target remains a fail-loud contract failure. Replay must not normalize
those divergences away to make a fixture pass.

## DevTools experience

The first DevTools surface is a read-only scrubber over one bounded browser
capture:

- one row per sequence with channel, phase, route pattern, and typed intent;
- nesting for Stream, Suspense, OOB, and SSE child observations;
- filters for request mode, target, return type, and compiled transition;
- a visible “truncated” marker when the ring buffer wrapped;
- export through the versioned redaction gate; and
- comparison with a locally selected artifact.

Selecting an earlier row highlights the recorded metadata; it does not rewind
the live DOM. A future isolated replay iframe may display an execution replay
driven by a test fixture, but DevTools must never repeat a mutation against the
currently open application merely because the user moved the scrubber.

## Ordering, concurrency, and lifecycle

One capture owns one monotonically increasing sequence. Allocation and append
occur under the same lock/publication boundary. A timestamp is never a
tie-breaker.

Thread-local or task-local buffers may prepare observations, but publication
must copy immutable data into the capture. No mutable request, response,
context, handler, template, or registry object survives in the timeline.

The capture has explicit bounds by record count and encoded byte size. When a
bound is reached it either stops with `truncated=true` or evicts from the front
and records the first retained sequence. It never silently claims the retained
suffix is a complete session.

Capture state belongs to debug/test runtime lifecycle and is discarded on app
shutdown. No registry mutates after freeze. Durable storage, multi-worker
aggregation, cross-instance ordering, and upload are not part of the first
implementation.

## Failure behavior

- Schema errors name the artifact path, schema, and invalid field.
- Sequence gaps, duplicates, and invalid parent links fail artifact validation.
- A redaction scan failure prevents export and names the field class, not the
  secret value.
- An unknown fixture driver or step fails before any action executes.
- A setup failure produces no partial replay mutation.
- A driver failure stops subsequent steps and runs teardown.
- A semantic mismatch reports the first causal divergence plus bounded
  downstream differences.
- A wrapped capture is explicitly incomplete and cannot satisfy whole-flow
  assertions.

No failure path emits an empty HTML swap or alters application response
handling.

## Rollout

### Phase 0: current RFC

- record the source audit and terminology;
- separate observation replay from execution replay;
- define privacy, ordering, and mutation boundaries; and
- ship no behavior.

### Phase 1: private observation model

- #647: add frozen private observation records and allocate ordered sequences
  in a bounded debug/test capture;
- #647: adapt existing HTTP and SSE traces without changing response semantics
  or retaining bodies, headers, cookies, sessions, HTML, or context;
- #648: add the versioned redacted artifact loader and comparator; and
- #649: add separately reviewed transport/browser correlation.

This phase changes debug protocol and must receive a separate review.

### Phase 2: Stream, Suspense, OOB, and browser correlation

- record structural lifecycle observations at existing transport boundaries;
- correlate browser settle/history/View Transition events;
- add the read-only DevTools scrubber; and
- prove one 10-step htmx flow with an OOB update.

Touching Suspense instrumentation or rendering requires the render-pipeline
check-in and end-to-end fail-loud proof required by the repository constitution.

### Phase 3: fixture-driven execution replay

- design the test-only fixture driver protocol;
- run in a fresh app/database/browser lifecycle;
- compare typed observations and domain assertions;
- check in one bug-reproducing Lucky Cat fixture; and
- prove teardown and mutation isolation.

Any public testing type, top-level export, or CLI command requires its own API
review, docs, changelog, and compatibility classification.

### Phase 4: production research

Issue #345 may reuse the artifact envelope only after separate decisions on
sampling, retention, multi-worker collection, redaction policy, access control,
and deletion. Phase 4 is not implied by shipping phases 1–3.

## Required implementation proof

1. A 10-step htmx flow with one OOB response produces a total, stable sequence.
2. Stream, Suspense, and SSE children link to the correct parent observation.
3. Concurrent requests cannot publish duplicate or reordered sequence values.
4. The capture marks wrap/truncation and rejects complete-flow assertions.
5. Dynamic route values, query strings, bodies, cookies, sessions, context
   values, SSE data, HTML, absolute paths, and secrets are absent from exports.
6. Debug-disabled and production-default apps allocate no capture store,
   endpoint, header, script, or background work.
7. Observation replay performs no imports, requests, DOM writes, or mutations.
8. Execution replay refuses unknown drivers/steps before invoking application
   code.
9. A mutation fixture runs against isolated state and always tears down.
10. A known ordering/empty-swap regression fails with a causal semantic diff.
11. Program fingerprint drift is explicit and never silently rewrites a fixture.
12. Existing SSE reconnect behavior remains application-owned and unchanged.

## Rejected alternatives

### Capture rendered HTML or DOM snapshots

Rejected as the generic contract. It records private user content, makes DOM
mutation the authority, and permits a wrong render path to look correct.
Application-specific browser assertions may still inspect safe rendered output.

### Hash context values and call the flow deterministic

Rejected. A hash cannot reconstruct database state, external responses, time,
randomness, or a request body. It can also leak low-entropy values through
guessing. The base artifact excludes context values entirely.

### Replay captured HTTP requests automatically

Rejected because traces intentionally omit necessary inputs and automatic
repetition can duplicate side effects. Explicit fixture drivers own actions.

### Use a session cookie as timeline identity

Rejected because anonymous diagnostics must not create application session
state or defeat shared caching. Debug capture scope is separate and temporary.

### Order by timestamp

Rejected because clocks and concurrent publication do not provide a stable
total order. Sequence allocation belongs to the trace publication boundary.

### Persist every timeline in the server

Rejected because it introduces per-client server view state, retention and
privacy obligations, multi-worker inconsistency, and unbounded storage.

### Reuse the timeline as SSE recovery storage

Rejected by RFC 007's application-owned replay boundary. Diagnostic evidence
is not a durable business event log.

### Add `chirp replay` in the first increment

Rejected until artifact compatibility, driver authority, mutation isolation,
and error behavior are proven through private testing seams. A CLI command is
public behavior and requires separate approval.

## Non-goals

- undoing database mutations from DevTools;
- reconstructing arbitrary production sessions;
- generic traffic mirroring or load testing;
- storing rendered HTML, DOM snapshots, or application payloads;
- replacing structured logging, OpenTelemetry, APM, or browser tests;
- guaranteeing deterministic business logic without fixture-controlled inputs;
- publishing the private `HypermediaProgram`;
- changing return types, render negotiation, OOB, Suspense, Stream, or SSE
  semantics;
- adding production capture as a side effect of debug/test work.

## Collateral and status

This RFC is the canonical design record. The #647 increment is private
debug/test infrastructure, so it needs no README, public API, site, example,
scaffold, migration, benchmark, or changelog update and documents no available
command.

No changelog: #647 and #648 change private debug/test capture internals only and
add no public API, configuration, CLI, production behavior, route execution, or
artifact compatibility promise.

## Decision gates for implementation

Maintainer approval for #647 covers only the private observation schema,
debug/test capture scope, and allowlisted copying described above. Before #648,
maintainers must approve the artifact schema, loader, comparator, and redaction
gate. Before #649, the rendering and DevTools stewards must approve lifecycle
instrumentation. Before phase 3, maintainers must approve any testing protocol
or public artifact API. Before any production use, issue #345 requires an
independent security and operations review.

# RFC 018: Signal dataflow graph

**Status:** Proposed

**Issue:** [#343](https://github.com/lbliii/chirp/issues/343)

**Last audited:** 2026-07-08

**Shipping impact:** None. This RFC does not change runtime behavior, public API,
CLI commands, template syntax, contract categories, or default severities.

## Summary

Chirp should compile signal declarations, derived dependencies, template sinks,
and connection ownership into one immutable dataflow graph at freeze time. The
graph should answer a stronger question than today's independent checks:

> Can every live value travel from one declared producer, through zero or more
> derived nodes, to a valid sink owned by a live connection?

The first implementation should remain private and feed `app.check()` and
Chirp DevTools. A public graph API, a new `chirp` command, Graphviz output, or a
severity change each requires a separate design review.

## Why a graph, and why now

The framework already owns every relevant surface:

- `SignalRegistry` records primary and derived producers;
- Kida templates contain `signal()`, `signal_block()`, `signal_bind()`, legacy
  `sse-swap`, and htmx 4 `data-chirp-signal` sinks;
- `signal_connect()` establishes the shared `/_chirp/live` transport;
- `app.check()` already compares registered names with template bindings; and
- DevTools already receives signal trace events.

The facts are currently stored and checked in separate subsystems. That is
enough to catch many misspellings, but it cannot explain end-to-end reachability
or distinguish an intentionally internal producer from a genuinely unused one.

## Current implementation audit

This section records behavior on `main` at `9ada3ba4` rather than proposed
behavior.

### Producer graph

`src/chirp/realtime/signals.py` owns `SignalSpec`, `DerivedSpec`, and
`SignalRegistry`:

- a primary name has exactly one producer;
- a derived name may depend only on already-registered primary or derived names;
- `_dependents` is the reverse edge index used for recomputation;
- `expand_connection_topics()` follows derived dependencies so a bound derived
  value activates its sources;
- audience, current values, and mutable maps are lock-protected; and
- `ReactiveBus` supplies bounded fan-out and latest-wins coalescing.

Registration order currently prevents a derived-signal cycle: a dependency must
already exist, so a new node cannot point to itself or a later node. This is a
useful invariant, but it is implicit in registration rather than represented in
the compiled application model.

### Template binding graph

`src/chirp/contracts/rules_signals.py` independently scans template source. It
recognizes helper calls, legacy `sse-swap`, htmx 4 signal markers, composed
layouts, and the `/_chirp/live` connection. It currently reports:

- `signal_dead_binding` as `ERROR` when a sink has no producer;
- `signal_orphan` as `INFO` when a registered name has no direct template sink;
- raw-marker guidance as `INFO`; and
- connection budget, session scope, and mixed-audience findings in adjacent
  rules.

These defaults remain unchanged by this RFC.

### A separate reactive dependency graph

`src/chirp/pages/reactive/index.py` maps changed context paths to Kida blocks and
supports derived paths. `src/chirp/contracts/rules_reactive.py` validates block
existence, emitted paths, audience scopes, and derivation cycles. That graph is
for context-path invalidation, not `@app.signal` fan-out. The two concepts may
share graph utilities later, but they must not be conflated.

### Compiler gap

`src/chirp/app/hypermedia_program.py` currently models routes, templates,
blocks, targets, and their transitions. It does not contain signal producers,
derived dependencies, bindings, connection ownership, audience, or coalescing
policy. `ContractCheckSnapshot.signal_names` carries only a flat set alongside
the program.

The result is a split-brain check: producer dependencies are known in one place
and direct sinks in another.

### Lucky Cat receipt

The public Lucky Cat example is the right canary because it contains primary,
push, derived, global, and session-scoped signals. Freezing
`examples.chirpui.lucky_cat.app:app` on 2026-07-08 produced:

- 10 registered names;
- five derived nodes;
- five primary source specs;
- four session-scoped names; and
- five derived edges: `lobby_snapshot` feeds `market_stats`, `movers`, and
  `featured`; `notifications` feeds `notif_badge` and `notif_announce`.

The exact receipt command was:

```bash
PYTHONPATH=. .venv/bin/chirp check \
  examples.chirpui.lucky_cat.app:app --json --include-info
```

It scanned 273 templates and returned no signal error, but it emitted this
informational finding:

```text
signal 'lobby_snapshot' is registered but no template binds it ...
```

That producer is not orphaned: it is an intentionally internal source for three
bound derived signals. A graph reachability check would classify it correctly.

## Decision

Compile a private, immutable signal subgraph from setup-time registrations and
static template evidence. The graph is part of the frozen application truth,
not a second mutable registry and not a client-side reactive store.

### Node kinds

The internal model needs four semantic node kinds:

| Kind | Identity | Evidence |
| --- | --- | --- |
| primary producer | signal name | `SignalSpec` registration |
| derived producer | signal name | `DerivedSpec` registration |
| binding | template plus stable source occurrence | helper call or approved static marker |
| connection | logical template connection owner | `signal_connect()` or approved static connection |

Names identify producers because duplicate producer names already fail during
registration. Bindings require occurrence identity because one signal may be
bound many times by design.

### Edge kinds

The minimum useful edge set is:

| Edge | Meaning |
| --- | --- |
| `depends_on` | a primary or derived producer supplies a derived producer |
| `renders_to` | a producer supplies a template binding |
| `owned_by` | a binding is inside or composed beneath a signal connection |
| `activates` | a connection topic closure activates a producer dependency |

`depends_on` and `renders_to` are semantic dataflow. `owned_by` and `activates`
describe delivery. Keeping them distinct lets checks explain whether a failure
is a missing producer, an unreachable sink, or a transport-ownership problem.

### Provenance

Every node and edge needs declared or inferred provenance plus a public-safe
source origin. The design should reuse the identity and provenance discipline in
`src/chirp/app/hypermedia_program.py`; it should not expose callable objects,
cached values, audience keys, or private runtime state.

### Freeze-time extraction

Compilation happens after registrations and template discovery are stable but
before runtime state is published:

1. snapshot every `SignalSpec` and `DerivedSpec` under the registry lock;
2. emit primary and derived nodes plus `depends_on` edges;
3. analyze reachable Kida templates for helper calls and approved literal
   markers;
4. resolve layout composition to connection owners;
5. emit binding and connection nodes plus delivery edges;
6. compute dependency and reachability closures; and
7. publish only frozen/slotted tuples with the application program.

The compiler must not mutate `SignalRegistry`, render templates, call signal
sources, run `initial()`, or inspect live values.

### Static and runtime evidence boundary

Static compilation is authoritative for declared producers, derived edges, and
literal/helper bindings. Dynamic template selection or dynamically computed
signal names cannot be guessed. Such surfaces need an explicit future
declaration tied to the compiler's existing dynamic-template declaration model,
or remain `unknown` rather than being reported as broken.

Runtime trace events may annotate a compiled graph with counts, last-update
times, queue pressure, and active connections in debug mode. Runtime evidence
must never silently rewrite the frozen topology or make a production check pass.

## Contract semantics

This RFC specifies intended categories but does not add or change them.

| Condition | Proposed result | Rationale |
| --- | --- | --- |
| binding has no producer | retain `signal_dead_binding` `ERROR` | update can never arrive |
| declared dependency is missing | immediate registration failure | already enforced |
| dependency cycle | `ERROR` if the future declaration model can express one | impossible delivery topology |
| producer has no path to any sink | `INFO` initially | valid headless/internal work may exist |
| producer reaches a derived node that reaches a sink | no orphan finding | transitive reachability is valid use |
| sink has no connection owner | `ERROR` only when composition proves it | visible live UI never updates |
| dynamic name or owner cannot be resolved | coverage gap / `INFO` | uncertainty is not corruption proof |
| non-coalescing path under measured pressure | runtime warning | static policy alone cannot prove overload |

Promoting, demoting, renaming, or splitting existing categories requires a
separate implementation review. In particular, this RFC does not alter the
current `signal_orphan` result even though the Lucky Cat receipt demonstrates
why its algorithm should later use transitive reachability.

## Backpressure

The graph may expose policy facts already present on `SignalSpec`:

- `coalesce=True` is latest-wins and drop-safe for state-like values;
- `coalesce=False` is append/drop-sensitive; and
- connection topic expansion determines which sources a page activates.

Static checks can explain these policies but cannot infer traffic rate or queue
health. Backpressure findings therefore require runtime counters from the
existing bus/trace path. No arbitrary static rate threshold belongs in
`app.check()`.

## DevTools view

DevTools should receive a public-safe projection of the frozen graph plus debug
telemetry. A minimal view should show:

```text
lobby_snapshot
  -> market_stats -> markets/page.html binding
  -> movers       -> markets/page.html binding
  -> featured     -> markets/page.html binding
```

Each node may show audience, coalescing policy, active/inactive state, update
count, and last error. It must not display session audience keys or payload
values by default. The panel is an inspection consumer, not the owner of graph
truth.

## Multi-worker consistency

The topology is deterministic setup state and should compile identically in
every worker from the same application revision. Cross-instance delivery is a
separate backplane concern.

When the backplane ships, deployment proof should compare a stable topology
digest across workers and report mismatches. Runtime update counts are expected
to differ; producer names, dependency edges, audience policies, and bindings are
not. This RFC does not design or require the backplane.

## CLI and export policy

The prototype sketch in #343 names `chirp check --signals`, but that flag does
not exist. This RFC does not add it and does not document it as usable.

The first graph projection should flow through existing structured inspection
work and DevTools. A later proposal may choose JSON or DOT export after the
private schema stabilizes. Graphviz must remain optional and generated from a
framework-owned neutral model; it must not become a core runtime dependency.

## Rollout

### Phase 0: current RFC

- record the source audit and Lucky Cat false-orphan receipt;
- define topology, provenance, and evidence boundaries; and
- make no behavior change.

### Phase 1: private compiler model

- add frozen/slotted internal signal nodes and edges;
- compile them at freeze without changing current check output;
- prove deterministic identities and free-thread-safe snapshots; and
- compare the compiled Lucky Cat graph with registry and template fixtures.

This phase touches the application compiler and requires the repository's
explicit design check-in before implementation.

### Phase 2: contract migration

- migrate binding checks to the compiled graph;
- preserve `signal_dead_binding` behavior;
- fix transitive orphan reachability;
- add composition-aware connection ownership checks; and
- record any category/severity decision separately with contract tests and
  changelog collateral.

### Phase 3: inspection

- expose a redacted projection to DevTools;
- add runtime counters as annotations, never topology mutations; and
- evaluate a stable export only after real consumers validate the schema.

## Required proof for implementation

1. A fixture with primary -> derived -> binding produces no orphan finding.
2. A misspelled helper binding retains `signal_dead_binding` `ERROR`.
3. Multiple bindings for one producer remain valid.
4. Layout composition resolves a page binding to its shell connection.
5. Dynamic evidence stays unknown until explicitly declared.
6. Frozen graph identities are deterministic across repeated builds.
7. Concurrent registration is rejected by the existing freeze boundary; graph
   reads are immutable under Python 3.14t.
8. Lucky Cat compiles to 10 producers and five derived edges, and the compiled
   binding set matches its reachable templates.
9. DevTools redaction tests prove no audience key or payload value leaks.
10. Multi-worker digest fixtures distinguish topology drift from telemetry.

## Rejected alternatives

### Keep independent flat checks

Rejected because a flat producer set cannot distinguish a transitive internal
producer from an orphan and cannot explain ownership paths.

### Reuse `DependencyIndex` directly

Rejected because context-path invalidation and named signal delivery have
different identities, lifecycle, and audience semantics. Shared graph
algorithms are possible; shared domain objects are not assumed.

### Discover the graph only at runtime

Rejected because it misses cold paths, makes correctness traffic-dependent, and
cannot support startup checks.

### Make Graphviz the canonical model

Rejected because DOT is an output format, not application truth, and would add
an unnecessary dependency to the core path.

### Infer arbitrary Python emit call sites

Rejected because call-site scanning is incomplete and fragile. Producer
registration and declared dependencies are authoritative; runtime emit traces
are observational evidence.

## Non-goals

- client-side stores or browser-owned reactivity;
- auto-observable Python values;
- executing signal sources during freeze;
- solving cross-instance fan-out;
- adding a public `SignalGraph` type;
- adding `chirp check --signals`;
- changing htmx 2/4 delivery syntax; or
- changing any default contract severity.

## Collateral

No changelog: proposed RFC only. No public API, site, example, scaffold, CLI,
or migration collateral moves until an implementation changes shipped behavior.

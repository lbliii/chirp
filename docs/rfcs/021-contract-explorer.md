# RFC 021: Contract Explorer

**Status:** Accepted; private static projection implemented by #652 and exact
finding-binding proof completed by #653

**Issue:** [#337](https://github.com/lbliii/chirp/issues/337)

**Parent saga:** [#335](https://github.com/lbliii/chirp/issues/335)

**Compiler saga:** [#503](https://github.com/lbliii/chirp/issues/503)

**Last audited:** 2026-07-08

**Shipping impact:** Private debug/test projection only. This RFC does not add a CLI flag, public graph or
inspection type, serialized schema, route, AppConfig field, contract category,
severity change, deploy gate, fuzzer, HTML artifact, or DevTools behavior.

## Summary

Chirp should turn its compiled hypermedia relationships, contract findings,
and observed runtime transitions into one navigable **Contract Explorer**. The
Explorer answers three different questions without pretending they are the
same:

1. **What is declared or inferred?** Routes, templates, named blocks, targets,
   and compiled transitions from the frozen application model.
2. **What is statically wrong or uncertain?** Existing `app.check()` findings,
   coverage counters, unresolved edges, and dynamic-analysis gaps.
3. **What was behaviorally exercised?** Debug/TestClient/browser observations
   correlated to stable compiled transition identities.

The Explorer is a projection over existing authorities. It is not another
scanner, renderer, route graph, or testing engine. It must never execute an
application route merely because that route is statically present.

The first implementation should remain debug/test-only and internal. A public
Python inspection API, versioned export, new `chirp` option, or deploy-blocking
policy requires its own compatibility and severity review.

## Current foundations

### Frozen compiler model

`src/chirp/app/hypermedia_program.py` defines the private, frozen, slotted
`HypermediaProgram`. It contains deterministic route, template, block, target,
and transition records plus source origins and declared/inferred provenance.
`src/chirp/app/hypermedia_program_compiler.py` publishes the complete program
once at the app freeze boundary.

RFC 008 explicitly keeps those dataclasses internal. The Explorer may copy
bounded public-safe scalar facts and opaque stable identities into a projection;
it must not export `HypermediaProgram` or make its records a supported query API.

The shipped program currently models four edge kinds:

- route to template;
- route to block;
- template to block; and
- target to block.

It does not yet represent every form, auth, OOB, Suspense, SSE, signal,
accessibility, or enhancement relationship described in the broader compiler
vision. The Explorer must label that coverage honestly instead of drawing
invented edges.

### Contract inspection

`src/chirp/cli/_check.py` calls `collect_check_json()` and returns a
JSON-compatible `InspectionResult` to the CLI, Milo MCP, and llms.txt surfaces.
The current stable payload contains:

- `ok`, route/template counts, and optionally contract coverage;
- ordered issue dictionaries with severity, category, message, route,
  template, and details; and
- legacy baseline/diff compatibility.

`src/chirp/contracts/serialize.py` still identifies a finding partly by human
message text. RFC 015 proposes stable finding/subject/location fields and a
versioned inspection profile, but that public API has not shipped. Therefore a
first Explorer must not guess an exact graph-node join from prose.

`src/chirp/cli/_routes.py` now supplies one structured route table across human
CLI, programmatic, MCP, and llms.txt use. It intentionally exposes only method,
path, handler label, and route name. It is not a compiler graph export.

### Private static projection

Issue #652 implements `src/chirp/contracts/explorer_projection.py` as a private,
frozen, slotted projection over one frozen `HypermediaProgram` and one finalized
`CheckResult`. It copies route, template, block, target, transition, finding,
coverage, and explicit analysis-gap facts into deterministically sorted tuples.
It does not accept an `App`, load a template, inspect a mutable registry, or
execute a handler.

Finding binding uses only the structured `ContractIssue.route` and
`ContractIssue.template` fields. A location that selects one node is `bound`, a
method-ambiguous path is `ambiguous`, and an absent or unknown location is
`unbound`. Issue #653 locks the important negative case: two findings may have
identical text containing real route and template names, yet the finding without
structured location remains unbound. No message token or substring participates
in correlation. The projection preserves the finalized category, severity,
message, route, template, details, and coverage values unchanged.

### Runtime transition evidence

`src/chirp/server/transition_trace.py` correlates debug return traces with the
frozen program. It records route, observation, request-mode, and relevant
transition identities without dynamic path or context values.

`src/chirp/testing/transitions.py` turns real debug responses into immutable
`TransitionObservation` and `TransitionCoverage` values. Coverage compares
only caller-declared expected modes and transition IDs. It does not claim that
a static edge was executed.

`src/chirp/testing/route_smoke.py` executes explicit `RouteSmokeCase` values
through `TestClient` and validates expected status/render intent. The caller
owns route parameters, method, body, headers, auth setup, and expected mode.
That explicit case boundary is the correct behavioral-exploration seam.

### Existing debug route explorer

`src/chirp/server/route_explorer.py` serves debug-only HTML at
`/__chirp/routes`. It serializes filesystem-page discovery objects and shows:

- URL, kind, methods, template, and selected metadata;
- layout/provider/action counts and details;
- handler signatures; and
- form-contract presence.

It does not consume `HypermediaProgram`, contract findings, structured CLI
inspection, or runtime transition evidence. It sees `discovered_routes`, not
the complete router surface, so it is a useful page inspector rather than the
authoritative application explorer.

`tests/test_route_explorer.py` proves that the endpoint exists only in debug
mode, filters page paths, and renders mounted page form contracts.

### Browser DevTools

`docs/devtools.md` documents bounded htmx, render-plan, Swap Doctor, SSE, View
Transition, and compiled-transition evidence. The browser can export records
and compare explicitly expected request modes. Runtime observations are the
behavioral layer the Explorer should overlay, not a replacement for static
compiler or contract facts.

## Problem statement

The current surfaces are individually useful but cannot answer a complete
question without manual correlation:

- the debug route page knows page-discovery details but not compiled edges;
- `chirp routes` knows router methods but not templates/targets/findings;
- `chirp check` knows findings but lacks stable subject IDs in its legacy shape;
- the private program knows stable topology but is not public inspection data;
- runtime traces know observed transitions but only for exercised requests;
- route smoke knows explicit cases but does not discover safe inputs; and
- DevTools records browser behavior but does not own the static application
  model.

Building another broad source scan would make these disagreements permanent.
Automatically walking routes would be worse: a route may require auth, tenant
state, path parameters, a body, a database fixture, or an external service, and
even a GET handler can have side effects.

## Decision

Build the future Explorer from one private immutable projection assembled from
already-frozen or already-finalized authorities:

```text
HypermediaProgram ---- topology/provenance ---+
                                                |
Inspection result ---- findings/coverage ------+--> ExplorerProjection
                                                |       |
Explicit observations - runtime evidence ------+       +--> debug UI
Explicit smoke cases -- declared test intent ---+       +--> test report
                                                        +--> future versioned artifact
```

The projection separates topology, findings, coverage gaps, and observations.
No consumer may infer one layer from another.

## Private projection model

The following is illustrative internal Python. This RFC does not approve
public names or field compatibility:

```python
@dataclass(frozen=True, slots=True)
class ExplorerNode:
    id: str
    kind: Literal["route", "template", "block", "target"]
    label: str
    provenance: Literal["declared", "inferred"]
    origin: str | None
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ExplorerEdge:
    id: str
    kind: str
    source_id: str
    destination_id: str
    resolved: bool
    provenance: Literal["declared", "inferred"]


@dataclass(frozen=True, slots=True)
class ExplorerFinding:
    severity: str
    category: str
    message: str
    subject_id: str | None
    route: str | None
    template: str | None
    remediation: str | None


@dataclass(frozen=True, slots=True)
class ExplorerEvidence:
    observation_id: str
    route_id: str
    request_mode: str
    transition_ids: tuple[str, ...]
    source: Literal["testclient", "browser", "debug"]


@dataclass(frozen=True, slots=True)
class ExplorerProjection:
    nodes: tuple[ExplorerNode, ...]
    edges: tuple[ExplorerEdge, ...]
    findings: tuple[ExplorerFinding, ...]
    coverage: tuple[tuple[str, int], ...]
    evidence: tuple[ExplorerEvidence, ...]
    analysis_gaps: tuple[str, ...]
```

Every collection is deterministically sorted. `attributes` is a closed,
kind-specific projection, not an arbitrary metadata bag.

### Source authority

| Explorer fact | Authority |
| --- | --- |
| route/template/block/target identity | `HypermediaProgram` |
| topology and resolved state | compiled transition edges |
| severity/category/message | finalized contract result |
| coverage counters | finalized `ContractCoverage` |
| request mode/observed edge | typed runtime transition trace |
| expected route invocation | explicit `RouteSmokeCase` or fixture driver |
| browser swap/history behavior | browser evidence |

The Explorer does not read mutable registries after freeze, rerun Kida parsing,
inspect handlers independently, or infer htmx behavior from rendered HTML.

## Finding correlation

Exact correlation requires a stable semantic subject ID. Until the separately
reviewed inspection-v1 identity work exists, the first projection uses two
honest levels:

1. findings with an exact route/template location may be grouped under that
   textual location; and
2. all other findings remain in an unbound findings panel.

It must not join a message to a node using substring matching. A route path or
template name can map to several method-specific or block-specific nodes; the UI
must show that ambiguity.

When stable subject IDs ship, the Explorer may copy them and bind directly.
The private program records still remain internal.

## Static topology view

The topology view displays only compiled relationships that exist:

- method-specific route nodes;
- logical template nodes;
- named blocks scoped to templates;
- normalized htmx target nodes;
- declared/inferred provenance;
- resolved/unresolved edge status; and
- public-safe logical origins where available.

The UI visually distinguishes:

- compiled and resolved;
- declared but dynamically resolved elsewhere;
- unresolved and diagnosed;
- inferred facts; and
- relationship families not yet represented by the compiler.

A blank area is not proof that an application has no forms, OOB, signals, or
auth. The projection includes explicit analysis gaps so incomplete compiler
coverage cannot masquerade as a clean graph.

## Findings and severity

The Explorer displays the exact finalized severity and category. It does not
promote a warning because a node is visually central, demote an error because a
runtime observation succeeded, or create a new “Explorer severity.”

Deploy posture remains the existing check policy. A future release/deploy gate
may consume the same inspection result, but this RFC neither adds nor changes a
gate. Every severity promotion still requires contract steward review, false-
positive proof, docs, and changelog collateral.

Runtime success never cancels a static error. One successful request cannot
prove every branch, authorization outcome, malformed input, missing block, or
fallback path is safe.

## Behavioral exploration

### Explicit cases only

The Explorer may ingest or run explicitly declared test cases. Each case owns:

- route and method;
- concrete path/query/body/header inputs;
- authentication/session/database fixture;
- expected status and render intent;
- expected request modes or compiled transition IDs; and
- teardown or transaction rollback.

Existing `RouteSmokeCase` is the first useful input. More complex form,
mutation, SSE, Suspense, or browser cases require separately designed fixture
drivers; the Explorer does not invent them.

### No automatic route fuzzing

The prototype phrase “fuzz/walk every valid `hx-*` path” is split:

- **walk** means traverse frozen static edges without executing handlers;
- **exercise** means run explicit cases through TestClient/browser;
- **fuzz** means generate inputs through an application-owned strategy with a
  deterministic seed and isolation boundary.

There is no generic “valid value” for an arbitrary Python path parameter, form
dataclass, auth policy, database identity, upload, or external dependency.
Chirp must never infer that GET/HEAD is side-effect-free enough to execute
automatically.

Property-based generation can be added later only for closed framework-owned
grammars or explicit application strategies. It must report its seed and never
run inside startup, `app.check()`, the production process, or a debug page
request.

## Coverage semantics

The Explorer reports three states per represented transition:

- **observed** — at least one real typed trace named the transition;
- **expected but unobserved** — a caller explicitly included the transition in
  a test expectation and no observation matched; or
- **not declared for behavioral coverage** — no claim either way.

“Not observed” is not automatically a failure. Static graph presence alone
does not define a complete test plan. Coverage becomes enforceable only when a
test/fixture explicitly declares expected modes and transition IDs.

Browser-only behavior—actual target existence, focus, history, htmx processing,
View Transitions, Alpine/islands, and SSE reconnection—requires browser evidence.
TestClient evidence cannot be relabeled as browser coverage.

## Debug user interface

The first user-facing implementation should evolve the existing debug-only
`/__chirp/routes` surface rather than add a second competing explorer route.
It may be renamed only through a compatibility review because the path is
documented in `docs/devtools.md` and site content.

The view should provide:

- topology, findings, coverage, evidence, and gaps as separate tabs;
- filter by route, template, block, target, category, severity, or mode;
- stable links between exact identities;
- a clear debug-only banner and current posture;
- no execute/mutate button in the topology view; and
- links to existing test commands or source-safe origins, not arbitrary file
  opening from the server.

The current route explorer embeds inline CSS, script, and serialized drill-down
data. A replacement must use the existing debug asset/CSP wiring, escape every
label, and avoid putting handler objects, source text, request values, or secret
details into HTML attributes.

## Static documentation artifact

A future opt-in static artifact may render the same versioned projection for CI
or docs. It is generated from structured facts, not scraped from the debug DOM.

The artifact is safe only when:

- its schema major and Chirp version are explicit;
- all source origins are public-safe and absolute paths are absent;
- auth/session/runtime values and rendered HTML are absent;
- no live debug endpoint or application secret is embedded;
- deterministic ordering makes drift reviewable; and
- a provenance block identifies which compiler/check/evidence layers were
  included and which were unavailable.

Publishing that schema or adding `chirp check --explore --format html` is a CLI
and compatibility decision. This RFC does not claim either command exists.

## Agents and structured access

The newly shipped Milo-backed `check`, `diff`, and `routes` operations already
give agents bounded read-only data. The Explorer should compose those
authorities after a versioned projection exists; it must not make agents scrape
HTML or expose private compiler objects through MCP.

The agent loop remains:

```text
inspect structured findings/topology
  -> choose one bounded repair
  -> run explicit contract/TestClient/browser proof
  -> compare findings and observed transitions
```

No Explorer action writes code, applies a repair, starts a server, mutates a
database, or changes contract policy automatically.

## Security and privacy

The debug UI exists only when `debug=True`, behind Chirp's reserved internal
route wiring. Production-default apps expose no Explorer route, data endpoint,
script, or trace store.

The base projection may contain:

- route patterns and methods;
- logical template/block/target names;
- opaque stable IDs and declared/inferred provenance;
- bounded contract messages/details already approved for inspection;
- public-safe module/qualname origins when deliberately included; and
- redacted runtime observation identities.

It excludes:

- dynamic path/query/body/form/upload values;
- cookies, sessions, auth tokens, users, tenants, and policy decisions tied to
  one request;
- context values, rendered HTML, database data, exception locals, and source
  text;
- environment variables, DSNs, absolute paths, and arbitrary object reprs;
- raw browser headers/body previews in a static public artifact; and
- executable links or commands derived from untrusted labels.

Debug-only visibility is not a substitute for escaping or redaction. A future
public artifact runs the repository public-safe scan and fails closed when an
unapproved field class appears.

## Lifecycle and free-threading

The static projection is built from one fully frozen program and one finalized
inspection result. It is a tuple of frozen records published atomically; request
threads never observe a partially assembled graph.

Runtime evidence is a separate bounded snapshot. Merging evidence into a view
creates a new immutable projection rather than mutating the frozen topology.
If several threads publish observations, the existing trace-store lock and
bounded-copy rules remain authoritative.

No explorer cache or registry mutates after app freeze. A future browser-side
view may retain local filters/selections, but those are not server application
state.

## Failure behavior

- Duplicate or invalid compiler identities continue to fail app freeze.
- Unresolved edges remain visible and retain existing contract diagnostics.
- A missing inspection result shows “findings unavailable,” never “clean.”
- A missing runtime trace shows “not observed,” never “passed.”
- Ambiguous textual finding locations remain unbound.
- Malformed observation/export data fails with its source and schema named.
- A renderer error returns the ordinary debug error page; it cannot affect the
  application route graph or emit an empty htmx swap.
- A public-safe scan failure blocks static artifact publication.

The Explorer cannot suppress an `app.check()` error or turn a failing deploy
gate green.

## Rollout

### Phase 0: current RFC

- record the source audit and authority map;
- define static, finding, and behavioral layers;
- reject automatic route execution; and
- ship no behavior.

### Phase 1: private immutable projection — implemented by #652 and #653

- copy supported compiler topology into private explorer records;
- attach finalized findings without guessed prose-to-node joins;
- include coverage counters and explicit analysis gaps;
- prove deterministic ordering, redaction, and freeze publication; and
- leave the existing route page unchanged.

This phase touches compiler/inspection consumers and requires a separate
implementation review.

### Phase 2: debug UI consolidation

- render the projection through the existing debug route/asset wiring;
- preserve page-route details that remain useful;
- add topology/findings/gaps views;
- escape/redact every field and prove debug-disabled 404 behavior; and
- keep all execution controls absent.

### Phase 3: observed evidence overlay

- ingest bounded typed transition observations;
- display observed/expected-unobserved/not-declared states;
- integrate explicit `RouteSmokeCase` results;
- add browser-only evidence without conflating it with TestClient proof; and
- reproduce one intentionally broken orphan htmx route/target path.

### Phase 4: versioned artifact and public surfaces

- design a versioned public-safe projection schema;
- decide whether a CLI option, standalone command, static site artifact, or
  DevTools export is justified;
- update public API/CLI compatibility, docs/site, tests, and changelog; and
- adopt deploy gating only through separately approved existing severities.

## Required implementation proof

1. Equivalent app registrations produce byte-stable private projections.
2. Routes, templates, blocks, targets, and represented edges match the frozen
   program exactly; unsupported relationship families are listed as gaps.
3. Findings preserve category, severity, message, location, details, and
   coverage without changing check behavior.
4. Findings without a stable exact subject remain visibly unbound.
5. An intentionally orphaned htmx route/target is found by the existing check
   and displayed without executing the handler.
6. Explicit normal, boosted, and targeted TestClient cases overlay the correct
   transition identities.
7. Browser-only swap/history/focus evidence is labeled separately.
8. No route executes during app freeze, `app.check()`, projection creation, or
   debug page rendering.
9. Debug-disabled and production-default apps expose none of the UI/data/assets.
10. Dynamic values, bodies, cookies, sessions, auth identities, HTML, secrets,
    and absolute paths are absent from the public-safe projection.
11. Concurrent observation publication cannot mutate or corrupt static topology.
12. Static artifact drift is detected from structured data, not an HTML snapshot.

## Rejected alternatives

### Expand the current route explorer scanner

Rejected as the authority. Its page-discovery objects and handler inspection
are useful details but cannot replace router/compiler/check/runtime facts.

### Expose `HypermediaProgram` directly

Rejected by RFC 008. Its records are internal compiler implementation and do
not provide a complete or stable public application graph.

### Join findings to nodes by message text

Rejected because wording is not semantic identity and can create false links.

### Automatically GET every route

Rejected because HTTP method is not a side-effect or fixture guarantee. Dynamic
inputs, auth, databases, and external services require explicit cases.

### Treat static reachability as test coverage

Rejected because a compiled edge proves possible structure, not successful
runtime/browser behavior.

### Generate docs by scraping the debug HTML

Rejected because presentation markup is not the data contract and may include
debug-only details unsuitable for publication.

### Add a new deploy severity profile for Explorer

Rejected. Existing contract policy remains authoritative; severity changes are
separate reviewed behavior.

### Let an agent auto-repair findings

Rejected as an Explorer responsibility. Structured evidence supports bounded
repairs, but code mutation remains an explicit developer/agent workflow.

## Non-goals

- a public compiler graph or arbitrary graph query language;
- automatic route/body/auth fixture generation;
- replacing Playwright, TestClient, `app.check()`, or contract diff;
- rendering application HTML or calling handlers from the Explorer;
- a production admin/debug endpoint;
- source-code navigation served from untrusted browser input;
- changing check messages, categories, severities, or deploy policy;
- claiming full graph coverage before compiler relationship families ship;
- adding a JavaScript build pipeline or SPA state store.

## Collateral and status

This RFC is the canonical design and private implementation record. It needs no
README, public API, site, example, scaffold, migration, benchmark, or changelog
update because the projection has no public consumer or available command.

No changelog: #652 and #653 add private debug/test projection and regression
proof only; they add no public API, CLI, configuration, route, severity change,
or production behavior.

## Decision gates for implementation

Before phase 1, maintainers must approve the private projection boundary and
its relationship to RFC 015 inspection identity. Before phase 2, the debug
route/DevTools/CSP changes require review. Before phase 3, any new fixture
driver or behavioral coverage policy requires testing and security review.
Before phase 4, every public schema, Python type, CLI option, static artifact,
or severity/deploy behavior requires the repository's explicit public-contract
check-in.

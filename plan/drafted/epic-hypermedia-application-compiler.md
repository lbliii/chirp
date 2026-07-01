# Epic: Hypermedia Application Compiler

**Status:** Draft north-star execution plan
**Updated:** 2026-07-01
**Strategy:** `docs/hypermedia-application-compiler.md`
**GitHub saga:** [#503](https://github.com/lbliii/chirp/issues/503)

## Objective

Turn Chirp's existing return-type, render-plan, contract-check, DevTools, and
static-export capabilities into one coherent hypermedia application compiler.

The compiler must serve full live applications first. It must support dynamic
request-time behavior including databases, forms, sessions, streaming, SSE,
tools, and AI. Static export remains an optional target for compatible routes.

## Invariants

- The return type remains the architecture.
- One template with named blocks remains the render contract.
- The live ASGI runtime is a primary compiler consumer.
- `chirp freeze` static export is one target, not the definition of the model.
- Existing render-plan behavior must not be replaced by a parallel pipeline.
- Static inference must fail honestly and allow validated declarations for
  dynamic behavior.
- Missing templates, blocks, targets, and non-optional OOB regions fail loud.
- Structured inspection, terminal output, DevTools, and tests must converge on
  the same facts.
- Public graph or inspection APIs require a design check-in, tests, docs,
  top-level export review, and changelog/migration collateral.
- Maintainer work must not absorb good-first issues #446-#458.

## Current Assets

- `AppCompiler` and the setup-to-runtime publication boundary.
- Immutable `RenderPlan` and typed-return normalization.
- `ContractCheckSnapshot`, structured `CheckResult`, and broad contract rules.
- Kida template/block metadata and dependency discovery.
- OOB, fragment-target, page-shell, signal, and settings registries.
- DevTools typed-return, render-plan, Swap Doctor, and SSE traces.
- TestClient helpers and end-to-end contract fixtures.
- `chirp freeze` static export.
- Furatena as a substantial downstream application and canary candidate.

## Steward Synthesis

### Raw Signals

Steward: App Lifecycle
Area: setup-to-runtime compilation and publication
Severity: P1
Invariant: Compiled application knowledge must be published once as immutable runtime truth; checks must not inspect half-built mutable state.
Evidence: `src/chirp/app/compiler.py:434`; `src/chirp/app/state.py:285`
User Impact: A graph built outside the lifecycle boundary could disagree with the router or expose partial state under concurrent startup.
Required Fix: Build the internal application model during the existing compiler boundary and publish it through runtime state or a stable snapshot.
Required Proof: Deterministic compilation, late-mutation rejection, idempotent freeze, and concurrency/lifecycle tests.
Collateral: Architecture docs and app lifecycle notes; no public API collateral until a graph view is exposed.
Confidence: High
Verification Status:
machine-verified

Steward: Rendering
Area: render plans and the single-template contract
Severity: P1
Invariant: The compiled model may describe rendering, but `RenderPlan` remains the request-aware execution authority and missing visible blocks continue to fail loud.
Evidence: `src/chirp/templating/render_plan.py:1`; `src/chirp/templating/render_plan.py:65`
User Impact: A parallel graph-driven renderer would create divergent full-page, fragment, OOB, Suspense, and SSE behavior and reintroduce silent DOM corruption risk.
Required Fix: Compile identities and relationships from existing composition/registry inputs, then correlate them with render plans instead of replacing the render pipeline.
Required Proof: Existing render-plan/OOB/Suspense contract suites plus new identity-correlation tests.
Collateral: DevTools and rendering docs when trace shapes become user-visible.
Confidence: High
Verification Status:
machine-verified

Steward: Contract Checks
Area: structured inspection and actionable diagnostics
Severity: P1
Invariant: Contract discovery must remain typed, low-noise, issue-first, and actionable; severity policy must not be silently coupled to serialization.
Evidence: `src/chirp/contracts/types.py:36`; `src/chirp/contracts/checker.py:445`
User Impact: If terminal output remains authoritative, downstream tools lose individual findings or rely on output capture and `SystemExit` translation.
Required Fix: Make one structured result authoritative and render terminal, JSON, CI, and downstream presentations from it.
Required Proof: Finding/count parity across clean, warning, error, deploy, and warnings-as-errors fixtures.
Collateral: Public API review, CLI docs, tests, top-level export decision, and changelog/migration notes when exposed.
Confidence: High
Verification Status:
machine-verified

Steward: Testing Helpers
Area: route smoke and transition coverage
Severity: P1
Invariant: Proof must exercise real routing, negotiation, middleware, and rendering; static analysis must not hide full documents in fragment targets.
Evidence: `src/chirp/testing/route_smoke.py:1`; `src/chirp/testing/assertions.py:1`
User Impact: Aggregate graph coverage could look complete while boosted, targeted, validation, or SSE behavior still fails in the browser.
Required Fix: Associate compiled transition identities with real TestClient request modes and preserve Playwright for DOM behavior.
Required Proof: Full/boosted/targeted route matrices, actionable assertion output, and an intentionally unexercised transition report.
Collateral: Testing docs, examples, scaffold tests, and browser-smoke policy.
Confidence: High
Verification Status:
machine-verified

Steward: CLI And Scaffolds
Area: `chirp check`, application startup, and static export
Severity: P1
Invariant: `chirp check` mirrors application diagnostics, while `chirp freeze` remains a distinct user-facing static-output command.
Evidence: `src/chirp/cli/__init__.py:235`; `src/chirp/cli/__init__.py:358`
User Impact: Calling all compilation “freeze” would misrepresent Chirp as a static-site generator and obscure its database-backed runtime.
Required Fix: Use application/startup compilation for the general model and reserve static export or `chirp freeze` for file materialization.
Required Proof: CLI/docs terminology audit and a mixed runtime/static-compatible demonstration.
Collateral: README, CLI/site docs, freeze docs, and scaffolds only when shipped behavior or public copy changes.
Confidence: High
Verification Status:
machine-verified

Steward: Narrative Docs
Area: product positioning and claim maturity
Severity: P2
Invariant: Public claims must distinguish shipped behavior from proposed graph APIs and must lead with full applications rather than compiler internals.
Evidence: `docs/hypermedia-application-compiler.md:1` -> `docs/philosophy.md:1`
User Impact: Premature “compiler” claims could create confusion or distrust if users cannot inspect a unified artifact yet.
Required Fix: Use the staged claim ladder and publish broad positioning only after the corresponding proof ships.
Required Proof: Content audit tracing claims to commands, APIs, tests, or explicitly marked roadmap statements.
Collateral: README/site/philosophy parity when issue #513 is unblocked.
Confidence: High
Verification Status:
machine-verified

Steward: Planning And Roadmap
Area: sequencing, dependencies, and backlog ownership
Severity: P1
Invariant: Compiler work must be dependency-ordered, preserve contributor-reserved issues, and record proof/collateral for every accepted item.
Evidence: `plan/roadmap.md:9`; `plan/drafted/epic-hypermedia-application-compiler.md:1`
User Impact: Treating the vision as one large rewrite would increase regression risk and obscure which increments provide independent value.
Required Fix: Execute through saga #503 and epics #504-#508 with explicit child issues, gates, and not-now items.
Required Proof: Live GitHub hierarchy, roadmap links, status hygiene, and issue-level acceptance criteria.
Collateral: Roadmap updates as items land; good-first issues #446-#458 remain untouched.
Confidence: High
Verification Status:
machine-verified

### Convergence

The stewards converge on an incremental consolidation around existing lifecycle,
render-plan, contract, CLI, and testing boundaries. No two stewards reported the
same defect finding, so the automatic P0 promotion rule does not apply. The
shared strategic constraint is that one compiled read model must serve existing
systems without becoming a second renderer or a static-only architecture.

### Minority Report

The rendering and CLI perspectives caution against describing Chirp simply as
“a compiler” before the unified artifact and proof loop ship. The accepted
wording is “a full-stack Python hypermedia framework with a built-in contract
compiler.” The stronger standalone category claim remains deferred to issue
#513.

### Ranked Compiler Backlog

| Rank | Issue | Reason | Confidence | Dependency |
| --- | --- | --- | --- | --- |
| 1 | [#497](https://github.com/lbliii/chirp/issues/497) boosted route smoke | Immediate user-visible regression protection and independent proof. | High | None |
| 2 | [#509](https://github.com/lbliii/chirp/issues/509) immutable program schema | Establishes the shared identities and provenance all compiler work needs. | High | Design check-in before code |
| 3 | [#498](https://github.com/lbliii/chirp/issues/498) dynamic reachability | Makes serious registry-driven consumers honestly compilable. | High | #509 identity/provenance direction |
| 4 | [#510](https://github.com/lbliii/chirp/issues/510) structured inspection | Unlocks downstream composition and consistent presentations. | High | Initial #509 schema; public API check-in |
| 5 | [#511](https://github.com/lbliii/chirp/issues/511) trace/coverage correlation | Closes the static/runtime/test proof loop. | Medium-high | #509 and #497 |
| 6 | [#500](https://github.com/lbliii/chirp/issues/500) Furatena canary | Converts a serious consumer into release evidence. | High | Can begin independently; richer output benefits from #510 |
| 7 | [#512](https://github.com/lbliii/chirp/issues/512) canonical application journey | Makes the full-application story teachable and testable. | Medium-high | #499 and selected proof-loop capabilities |
| 8 | [#501](https://github.com/lbliii/chirp/issues/501) example inventory | Keeps the expanding proof surface accurate. | High | Can run alongside #512 |
| 9 | [#513](https://github.com/lbliii/chirp/issues/513) public compiler proof | Productizes evidence after the claim is true. | Medium-high | Material progress on #504-#507 |

Issues #499 and #502 are active hygiene work already represented under the
relevant epics. They support the sequence but are not separate compiler design
gates.

## Workstream A: Compiler Core

**Outcome:** One immutable `HypermediaProgram`-style artifact represents the
application's routes, templates, blocks, targets, transitions, and origins.

**Required work:**

- Define internal node, edge, identity, and source-origin types.
- Compile existing registries and discovered template metadata into the model.
- Represent inferred versus explicitly declared facts.
- Add validated dynamic template/view reachability.
- Keep the model frozen and safe for shared runtime reads.
- Migrate checks incrementally; do not create a second permanent source of
  truth.

**Proof:**

- Deterministic graph snapshot tests.
- Duplicate/unknown identity failures.
- Furatena-style dynamic registry fixture without unreachable reference stubs.
- Free-threaded publication proof through immutability and lifecycle tests.

**Collateral:** contracts docs, architecture docs, DevTools schema notes, and a
changelog fragment when behavior becomes user-visible.

## Workstream B: Structured Inspection

**Outcome:** A structured application-inspection result is authoritative;
terminal, JSON, downstream tools, and CI render or evaluate that result.

**Required work:**

- Design a stable structured inspection seam.
- Preserve every diagnostic with severity, category, graph identity, source
  origin, and remediation.
- Make terminal output a presentation layer rather than the only public path.
- Define compatibility status for serialization and plugin extensions.
- Keep deploy posture and warnings-as-errors policy separate from discovery.

**Proof:**

- Terminal and JSON parity tests.
- Clean, warning-only, and error fixtures.
- Downstream composition test equivalent to `fura check --json`.
- No `stdout` capture or `SystemExit` translation needed by consumers.

**Collateral:** public API review, CLI docs, `docs/public-api.md`, testing
helpers, and migration notes if `app.check()` behavior changes.

## Workstream C: Static/Runtime Proof Loop

**Outcome:** Compiled transitions, runtime render plans, DevTools traces, and
test coverage share stable identities.

**Required work:**

- Attach compiled transition IDs to runtime render-plan traces.
- Add route smoke across normal, boosted, and narrow-target navigation.
- Report transition coverage rather than only aggregate object counts.
- Cover mutations, validation, no-JS fallbacks, OOB, Suspense, and SSE.
- Keep Playwright as behavioral proof for DOM outcomes static checks cannot
  establish.

**Proof:**

- A deliberately broken full-document-in-fragment fixture fails before release.
- DevTools trace IDs resolve to compiled transition descriptions.
- Coverage reports distinguish untested request modes for one route.
- Existing debug headers and export schemas remain bounded and documented.

**Collateral:** DevTools docs, testing docs, examples, CI, and browser-smoke
policy.

## Workstream D: Full-Application Evidence

**Outcome:** The compiler is proven against a serious database-backed
application rather than only static or isolated examples.

**Required work:**

- Add a pinned Furatena downstream compatibility canary.
- Establish one canonical application journey covering SQL, search, forms,
  validation, boosted navigation, OOB/SSE, security, and deployment checks.
- Keep example inventory and dependency requirements machine-validated.
- Clearly separate runtime-required and static-compatible routes.

**Proof:**

- Candidate Chirp wheel tested against a pinned downstream revision.
- Canonical journey tests full and htmx request modes.
- `chirp freeze` exports eligible content without implying runtime routes were
  converted to static behavior.
- Failures identify whether Chirp, the consumer, or the harness owns the fix.

**Collateral:** example READMEs, contributor setup, release policy, and public
positioning.

## Workstream E: Product Story And Adoption

**Outcome:** Developers understand the value in five minutes without needing
to understand compiler internals.

**Required work:**

- Lead with full application outcomes; use compiler as the differentiator.
- Publish a short database-backed proof with three intentionally broken edges.
- Explain dynamic runtime versus optional static export explicitly.
- Show `chirp check`, DevTools, and route-smoke as one feedback loop.
- Document target users and honest non-goals.

**Proof:**

- Every public claim traces to a shipped command, API, test, or marked roadmap
  item.
- The demonstration can be run from a fresh documented install.
- Static export is never described as the only or primary deployment model.
- The README/site message matches canonical philosophy and non-goals.

**Collateral:** README, site architecture/philosophy pages, examples, release
notes, and comparison guidance.

## Sequence

1. Compiler core schema and source origins.
2. Dynamic reachability declarations.
3. Structured inspection result and serializers.
4. Stable transition identity in runtime traces.
5. Transition-oriented route smoke and coverage.
6. Pinned downstream canary and canonical application journey.
7. Public positioning and graphical explorer after the underlying data is
   trustworthy.

The broader Contract Explorer RFC (#337) remains research until these
foundations provide stable graph data worth visualizing.

## Dependencies And Risks

| Risk | Mitigation |
| --- | --- |
| A second graph drifts from runtime behavior | Compile from existing registries and render-plan inputs; migrate consumers incrementally. |
| Static inference produces false confidence | Track provenance and require explicit declarations when behavior is dynamic. |
| Public graph types freeze internals too early | Keep the first model internal; design structured public views separately. |
| Marketing outruns implementation | Use the staged claim ladder in the strategy document. |
| Static export eclipses live applications | Require every proof and public description to show database-backed runtime behavior. |
| Contract checks become slow or noisy | Benchmark compilation, cache template analysis, and track false positives against downstream fixtures. |
| Graph identity leaks private source details | Define public-safe origins and redact filesystem/runtime-sensitive values. |

## Not Now

- A graphical Contract Explorer before stable structured graph data.
- Automatic business-logic generation.
- Replacing Playwright or real downstream tests with graph analysis.
- A generic client state/runtime abstraction.
- ORM, admin, job queue, email, or WebSocket expansion.
- Making internal compiler types top-level public API in the first increment.

## Completion Gates

- One authoritative compiled model is used by multiple contract domains.
- Dynamic consumer registrations are explicit and validated.
- Structured inspection is composable without terminal interception.
- Runtime and test evidence correlate with compiled transitions.
- Furatena and the canonical application journey pass against a built wheel.
- Public positioning accurately presents live applications and optional static
  export.
- Required docs, tests, examples, public API review, and changelog collateral
  accompany each user-visible increment.

## GitHub Mapping

| Workstream | Epic | Implementation issues |
| --- | --- | --- |
| Compiler core | [#504](https://github.com/lbliii/chirp/issues/504) | [#509](https://github.com/lbliii/chirp/issues/509) immutable program schema; [#498](https://github.com/lbliii/chirp/issues/498) dynamic reachability |
| Structured inspection | [#505](https://github.com/lbliii/chirp/issues/505) | [#510](https://github.com/lbliii/chirp/issues/510) inspection result and serializers |
| Static/runtime proof loop | [#506](https://github.com/lbliii/chirp/issues/506) | [#511](https://github.com/lbliii/chirp/issues/511) transition trace/coverage correlation; [#497](https://github.com/lbliii/chirp/issues/497) boosted route smoke |
| Full-application evidence | [#507](https://github.com/lbliii/chirp/issues/507) | [#512](https://github.com/lbliii/chirp/issues/512) canonical journey; [#499](https://github.com/lbliii/chirp/issues/499) test environment; [#500](https://github.com/lbliii/chirp/issues/500) Furatena canary; [#501](https://github.com/lbliii/chirp/issues/501) example inventory |
| Product story | [#508](https://github.com/lbliii/chirp/issues/508) | [#513](https://github.com/lbliii/chirp/issues/513) public proof; [#502](https://github.com/lbliii/chirp/issues/502) roadmap reconciliation |

GitHub sub-issue relationships are the live progress view. This plan preserves
the architectural rationale, sequencing, risks, proof, and collateral expected
from each item.

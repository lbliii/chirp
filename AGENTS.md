# Agent Constitution

## North Star

We build Chirp to prove Python web apps can stay hypermedia-native: the
server renders HTML, the browser renders UI, and typed return values connect
the two without a SPA, JSON serialization layer, or JavaScript build pipeline.
The project description, README, and philosophy all center HTMX, HTML
fragments, streaming HTML, and Server-Sent Events as first-class framework
behavior.

A single template with named blocks is the contract. Full pages, htmx
fragments, OOB updates, Suspense chunks, streaming HTML, and SSE payloads must
come from the same render surface unless a documented public API says
otherwise.

## Non-Negotiables

- The return type is the architecture. `Page`, `Fragment`, `OOB`,
  `Suspense`, `EventStream`, `ValidationError`, `FormAction`,
  `MutationResult`, `Action`, `Stream`, and `Redirect` drive negotiation,
  status, htmx awareness, and rendering.
- One template serves many access patterns. Named blocks are the unit; do not
  split a parallel partials system or REST serialization path to solve a
  hypermedia problem.
- `from chirp import ...` is the blessed public import path. New top-level
  names update `src/chirp/__init__.py`, `docs/public-api.md`, tests, and
  changelog/migration collateral.
- `AppConfig` is frozen and slotted. New fields are public API and require a
  design check-in, tests, docs, and environment-variable parity when relevant.
- Frozen/slotted dataclasses are the default for config, return types,
  validation results, freeze results, registry entries, and stable read models.
  Shared mutability needs an explicit lock, context boundary, or lifecycle
  boundary.
- `app.check()` is part of the product. New render wiring, page conventions,
  htmx behavior, OOB regions, Suspense behavior, SSE wiring, forms, and
  production-safety rules need startup checks where wrong usage is detectable.
- Fail loud when visible HTML can be corrupted. Missing OOB blocks raise
  `BlockNotFoundError`; non-optional orphan OOB regions are `ERROR`; empty
  swaps are trust bugs.
- Use the right streaming type: `Stream` for progressive first-byte HTML,
  `Suspense` for initial shell-plus-deferred OOB blocks, and `EventStream` for
  post-load SSE updates.
- Layouts use composition, not page-template inheritance. Pages render into
  the layout content block through render-plan composition; they do not
  override sibling layout blocks.
- Debug htmx/OOB/Suspense/SSE issues with Chirp DevTools before guessing:
  run with `debug=True`, open the app, press `Ctrl+Shift+D`, then inspect
  `window.ChirpHtmxDebug`.
- No silent `except`, unexplained `# type: ignore`, vague errors, speculative
  config, or undocumented public behavior.

## Architecture Boundaries

| Path | Steward / Contract |
| --- | --- |
| `src/chirp/` | Public API, `AppConfig`, top-level exports, root helpers |
| `src/chirp/app/` | Registration, freeze, lifecycle, runtime state, mounting |
| `src/chirp/http/` | Request/response/forms/cookies/headers/query primitives |
| `src/chirp/routing/` | Route matching, params, names, URL-generation inputs |
| `src/chirp/server/` | ASGI handling, negotiation, htmx, debug, sync path |
| `src/chirp/templating/` | Return types, Kida, render plans, OOB, Suspense |
| `src/chirp/contracts/` | `app.check()`, rule orchestration, severity policy |
| `src/chirp/pages/` | Filesystem pages, shells, sections, reactive pages |
| `src/chirp/middleware/` | Middleware protocol and built-in request pipeline |
| `src/chirp/security/` | Safe URLs, password, lockout, and security helpers |
| `src/chirp/cache/` | Cache protocols, backends, and cache middleware |
| `src/chirp/data/` | Optional data helpers, schema, migrations, query helpers |
| `src/chirp/realtime/` | SSE event types and post-load server-push helpers |
| `src/chirp/validation/` | Validation rules and form-result contracts |
| `src/chirp/cli/` | CLI commands, scaffolds, freeze/migration entrypoints |
| `src/chirp/testing/` | Public test client and assertion helpers |
| `src/chirp/docs/` | Docs plugin, autodoc, docs search, docs checks |
| `src/chirp/markdown/` | Markdown optional extra |
| `src/chirp/i18n/` | i18n optional surface |
| `src/chirp/ai/` | AI/LLM optional extra and streaming helpers |
| `src/chirp/ext/` | Extension adapters, especially `chirp-ui` |
| `src/chirp/tools/` | MCP/tool registry, schema, handler, event surface |
| `tests/` | Test suite ownership and regression proof |
| `tests/contracts/` | End-to-end `app.check()` contract coverage |
| `examples/` | Executable docs and scaffold-pattern proof; see **Example comment budget** in `examples/AGENTS.md` |
| `docs/` | Narrative docs, RFCs, release policy, public API notes |
| `site/` | Bengal docs site source and generated-output boundary |
| `benchmarks/` | Performance methodology and benchmark claims |
| `changelog.d/` | Towncrier fragment inputs |
| `plan/` | Roadmap, backlog, and not-now artifacts |

## Governance Alignment

- No `.github/CODEOWNERS`, `OWNERS`, or `MAINTAINERS` file exists in this
  repository today. Human review routing is manual-confirmation-needed until
  one is added.
- Stewards advise. Human reviewers approve.
- Canonical public knowledge lives in `README.md`, `docs/`, `site/content/`,
  `docs/public-api.md`, and `docs/release-policy.md`.
- Release and build governance lives in `pyproject.toml`, `uv.lock` when
  present, `.github/workflows/`, `.pre-commit-config.yaml`, `Makefile`,
  `CHANGELOG.md`, and `changelog.d/`.
- Generated site output under `site/public/` and Bengal cache/output under
  `site/.bengal/` are not source-of-truth unless a scoped steward explicitly
  says a generated artifact must move with source.

## GitHub Issues

Maintainer and agent work must **not** take good first issues. Those issues exist
for external contributors.

- Skip any issue labeled `good first issue` or titled `[GF] ...`.
- Do not implement, close, or batch-plan GF work during triage unless a
  contributor opened the PR and maintainers are reviewing it.
- Epic [#446](https://github.com/lbliii/chirp/issues/446) (*Learn Chirp by
  building*) and its children (#447–#458) are all GF — leave them for
  contributors.
- When picking maintainer batches, prefer unlabeled or epic/P1/P2 roadmap issues
  (for example AI Phase 2 #431–#438, Horizon RFC drafting, Lucky Cat framework
  work without the GF label).

## Stop And Ask

Check in before:

- Changing public API, protocol shapes, return-type semantics, top-level
  exports, plugin protocols, CLI commands, scaffold defaults, or documented
  compatibility tiers.
- Adding a return type, `AppConfig` field, mandatory runtime dependency,
  optional extra, migration surface, release/build surface, or public config
  flag.
- Touching the render pipeline: `templating/render_plan.py`,
  `templating/returns.py`, `templating/suspense.py`, OOB/Suspense block
  discovery, ancestor pruning, or `BlockNotFoundError` propagation.
- Promoting/demoting `app.check()` severities or changing default contract
  semantics.
- Changing data models, schema/migration output, cache-key semantics,
  auth/security behavior, lifecycle/freeze behavior, or free-threaded shared
  state.
- Touching the sync fast path (`App.handle_sync`, `SyncRequest`, pre-encoded
  content types) without a measurement plan.
- Performing irreversible operations, deleting dead-looking code, or resolving
  test/code disagreement.
- Fixing a bug you cannot reproduce; ask for a minimal repro or environment
  dump.

## Anti-Patterns

- Adding `make_response()`, `jsonify()`, `to_json()`, or a REST-style side
  channel to solve a hypermedia return-type problem.
- Using `{% if key %}` for Suspense deferred values. Use
  `{% if key is deferred %}` or `"key" in __chirp_defer_pending__`.
- Using bare jsDelivr package URLs for Alpine/plugins. Use explicit
  `/dist/cdn.min.js` URLs or Chirp's injection helpers.
- Setting `optional=True` on an OOB region to hide a typo.
- Mutating registries after freeze.
- Putting route dispatch, rendering, app lifecycle, and middleware concerns in
  one package because it is convenient.
- Refactoring adjacent issues during a bug fix unless the refactor is the fix.
- Adding speculative `AppConfig` fields before the pre-1.0 audit resolves their
  public contract.

## Steward System

Agents read this root file plus the closest scoped `AGENTS.md` for every file
they edit. Root is the constitution, routing guide, and swarm protocol. Scoped
files are domain stewards.

Each steward has:

- Point Of View: who or what the domain represents.
- Protect: grep-verifiable invariants and failure modes.
- Contract Checklist: concrete files and tests to inspect when the domain
  changes.
- Advocate: concrete near-term investments this domain should push for.
- Own: code, tests, docs, agent artifacts, and CODEOWNERS status.
- Optional Do Not and Serve Peers sections only when they add non-obvious local
  guidance.

Cross-boundary PRs include **Steward Notes** naming consulted steward files,
accepted/deferred findings, required proof, collateral updates, and dissent.

### Contract Checklist

For cross-surface changes, identify every surface that should agree: API/CLI,
programmatic use, protocol, schema/types, UI, docs, examples, scaffolds,
templates, tests, benchmarks, changelog, site content, and generated artifacts.

Every accepted finding must name required proof and collateral updates, or say
`no collateral: <reason>`. Docs/examples/scaffold changes move in the same PR
as user-facing behavior unless synthesis records why they are unaffected.

### Steward Signal Format

Use this exact format for findings:

```text
Steward:
Area:
Severity: P0/P1/P2/P3
Invariant:
Evidence: <source-file:line> [-> <doc-file:line> for content audit]
User Impact:
Required Fix:
Required Proof:
Collateral:
Confidence:
Verification Status:
machine-verified / manual-confirmation-needed / not-machine-verifiable
```

Machine-verified means the reviewer can reproduce the grep, test, command, or
source read. If a line number or factual claim was not checked, mark it
manual-confirmation-needed.

### Convergence Rule

Two or more independent stewards flagging the same accepted finding
automatically
promotes it to P0 for synthesis. The implementing agent may still defer it, but
the PR notes must explain why.

### Steward Swarms

Trigger phrases for implementation review: `ask stewards`, `bugbash`,
`review swarm`, and `steward synthesis`.

Trigger phrases for content review: `audit docs`, `content audit`, and
`accuracy pass`.

When delegation is available:

- Spawn independent steward agents for affected domains.
- Each steward reads root plus its closest scoped file.
- Each steward advocates only for that domain.
- Each steward returns findings in the Steward Signal Format.
- The implementing agent owns synthesis and final decisions.
- Apply the Convergence Rule.
- Spot-check P0/P1 findings for the Unverified Finding Regression before
  applying them.

For backlog, roadmap, or prioritization work, consult all relevant scoped
stewards and produce raw steward signals, confidence, dependencies, risks,
convergence, minority reports, ranked backlog, and not-now items.

### Global Sweep On Accepted P0s

When a P0 is accepted, grep the entire code/docs/examples/site tree for the
same wrong claim or pattern before closing it. Record the command or search
pattern in PR notes or `STEWARD_AUDIT.md`.

## Cross-Cutting Concerns

### Hypermedia Fail-Loud Behavior

Applies when touching return types, negotiation, templates, OOB, Suspense, SSE,
forms, htmx targets, DevTools, examples, or docs. Evidence required: a test or
contract check that exercises the user-visible path, preferably through
`TestClient` or `app.check()`.

### Free-Threading And Shared State

Applies when touching registries, middleware state, cache backends, data pools,
reactive buses, tool events, context helpers, lifecycle hooks, or runtime
publication. Evidence required: immutability, context isolation, a lock, a
documented lifecycle boundary, or a concurrency test.

### Optional Dependencies

Optional extras stay optional. Missing extras produce actionable install
guidance and do not break core imports. Evidence required: dependency group in
`pyproject.toml`, allowed unresolved imports when needed, import-error tests for
missing extras, and docs/examples that install the required extra.

### Public API And Release Contract

Stable API breaks require deprecation or documented pre-1.0 migration guidance.
Provisional changes still need changelog coverage. Evidence required: update
`src/chirp/__init__.py`, `docs/public-api.md`, tests, README/site when relevant,
and `changelog.d/`.

### Generated Artifacts

Do not hand-edit generated site/cache output unless the scoped steward says the
artifact is source-of-truth. Evidence required: source change plus build or
explicit no-build rationale.

### Public-Safe Filter

Before finalizing agent-authored files, grep for customer names, private team
member names, internal project/cluster names, private quotes, and specific
internal scale/cost numbers. Replace them with public, source-backed framing.

## Known Regression Patterns

- **Fabricated CLI / config fields.** Verification: every flag traces to
  `argparse`, `AppConfig`, Pydantic/config schema, or command implementation.
  Grep source before documenting.
- **Unverified finding regression.** A reviewer reports a divergence that a
  source grep would have disproved. Verification: every factual P0/P1 carries
  `machine-verified`, `manual-confirmation-needed`, or
  `not-machine-verifiable`.
- **Narrow-fix regression.** A P0 corrected on one page survives on sibling
  pages. Verification: every accepted P0 closure runs the Global Sweep above.
- **Silent empty swap regression.** OOB/render failures become empty HTML and
  wipe visible DOM. Verification: missing-block tests assert
  `BlockNotFoundError`, no empty `hx-swap-oob` wrapper for non-optional
  missing blocks, and `app.check()` coverage.
- **Suspense falsy regression.** Deferred values such as `[]`, `0`, or `""`
  render as if still pending. Verification: templates use `is deferred` or
  `__chirp_defer_pending__`, and contract tests cover falsy resolved values.
- **Full document in fragment target.** htmx requests receive a full page in a
  narrow target. Verification: `Page`/`Fragment`/`MutationResult` tests cover
  htmx and non-htmx branches and assert render intent/no full document.
- **Optional-extra drift.** Examples/docs omit an extra that code imports.
  Verification: install commands include the extra or direct dependency, and
  missing-extra tests assert actionable messages.
- **Invalid Python 3.14 syntax churn.** Formatter/linter changes introduce
  syntax that import-time checks catch. Verification: `uv run ruff check .`,
  `uv run ty check src/chirp/`, and import-focused tests for touched modules.
- **Scaffold/example drift.** Generated projects teach unsafe or outdated
  patterns. Verification: scaffold runtime tests, example tests, and README/site
  snippets move with scaffold changes.
- **Benchmark overclaim.** Performance docs imply production conclusions from
  synthetic workloads. Verification: benchmark methodology, environment,
  caveats, and latest artifact are cited.

## Done Criteria

- `uv run ruff check .` and `uv run ruff format . --check` are clean, unless
  the change is docs-only and a narrower markdown/tooling check is recorded.
- `uv run ty check src/chirp/` is clean when Python code or public typing
  changes.
- `uv run pytest` passes for release-class changes; use the narrowest relevant
  subsets first while developing.
- Coverage stays at or above 80 percent for code changes.
- Hypermedia surface changes include end-to-end `tests/contracts/` coverage
  through `TestClient` or `app.check()`.
- Tests exercise the interesting path: htmx vs non-htmx, missing block,
  awaitable vs sync context, malformed form, production vs debug, and optional
  dependency absent/present where relevant.
- Public API changes include a towncrier fragment in `changelog.d/` and
  migration notes if behavior breaks.
- Docs/changelog/migration notes, examples/scaffold/templates, benchmarks, and
  performance/concurrency/security notes move with behavior where relevant.
- Every accepted steward finding has proof or an explicit no-impact note.
- Error messages name what to fix: template, block, route, selector,
  registration, config flag, import string, dependency extra, or migration
  command.

## Review Notes

- PR titles usually use `feat:`, `fix:`, `refactor:`, `build:`, or `deps:` in
  imperative voice, but clarity matters more than prefix.
- Keep one concern per PR unless a concept rename across many files is the safer
  review unit.
- Flag surprises: weird tests, unused public names, suppressions, dead-looking
  code, benchmark gaps, free-threading assumptions, steward disagreement, and
  deferred/not-now findings.
- Put the why in the PR description. Let the diff show the what.

## When This File Is Wrong

Update it. Root and scoped `AGENTS.md` files are first-class project artifacts;
they should evolve when evidence proves current guidance misses real failures
or creates noise.

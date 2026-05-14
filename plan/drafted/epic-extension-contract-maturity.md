# Epic: Extension Contract Maturity

**Status**: Draft follow-up, not shipped behavior
**Updated**: 2026-05-14
**Source**: ChirpUI 0.9 upgrade review, PR #133 steward synthesis, optional-extra docs drift audit
**Scope**: Optional extension adapters and extras: ChirpUI first, then markdown, AI, Redis/session, and data-pg
**Not Target**: Making optional extensions core dependencies or building a generic plugin framework rewrite

---

## Problem

The ChirpUI 0.9 upgrade showed that optional extensions can be installed,
importable, configured, and runtime-ready as separate states. Chirp had partial
defense in depth for installed ChirpUI templates and filters, but the runtime
contract still depended on a separate `use_chirp_ui(app)` call for static
assets, Alpine controllers, page-shell targets, OOB regions, route-aware link
globals, and ChirpUI-specific checks.

That is the reusable pattern to mature: optional extensions should stay
optional, but their readiness boundary should be explicit, diagnosable, and
tested.

## Invariants

- Chirp core does not gain mandatory dependencies for optional surfaces.
- `use_*` adapter helpers are the recommended runtime wiring path when an
  extension needs more than imports.
- Installed package fallbacks may improve ergonomics, but they must not hide a
  missing runtime/configuration contract.
- Missing optional dependencies produce actionable install/version guidance.
- `app.check()` catches wrong wiring when the app has enough static evidence.
- Current docs and examples use current package names and blessed adapter
  paths; historical release notes and RFCs remain historical unless explicitly
  revised.

## Ranked Work

### 1. ChirpUI Adapter Contract Finish

**Goal**: Make `use_chirp_ui(app)` the sole current recommended runtime path
while keeping direct ChirpUI package APIs available for advanced users.

**Scope**:
- Document direct `chirp_ui.register_filters(app)` as redundant for normal
  Chirp apps once `use_chirp_ui(app)` is active.
- Add fake-module or monkeypatch tests for an old/incomplete `chirp_ui`
  package so capability/version errors stay readable.
- Keep route-aware globals from overriding user-defined globals.
- Keep contract categories stable enough for severity overrides.

**Required proof**:
- `uv run pytest tests/test_chirpui_boundary.py tests/test_templating_filters.py -q`
- `uv run pytest tests/contracts/test_custom_checks_integration.py -q -k chirpui`
- Error-message assertions for missing required ChirpUI 0.9 surfaces.

**Collateral**: ChirpUI docs, example README snippets, contract category docs,
and changelog if behavior changes.

### 2. Contract Category Reference For Optional Extensions

**Goal**: Make optional-extension diagnostics discoverable enough that app
authors can use `override_contract_severity()` intentionally.

**Scope**:
- Add a site docs table for optional-extension categories such as
  `chirpui_runtime`, `chirpui_components_unavailable`,
  `design_system_summary`, `design_system_descriptor`, and
  `design_system_manifest`.
- Include severity, emitted condition, likely fix, and whether the category is
  safe to promote to ERROR in CI.
- Cross-link from ChirpUI setup docs and contract-debugging docs.

**Required proof**:
- `uv run pytest tests/docs -q`
- `uv run pytest tests/docs/test_site_link_drift.py -q`
- An `rg` or test-backed check that documented emitted categories still exist
  in contract/terminal output mappings.

**Collateral**: Site contract docs and any README quick-reference if category
guidance becomes prominent.

### 3. Optional Extra Install Guidance Guardrails

**Goal**: Prevent docs, examples, scaffolds, and runtime errors from drifting
across package names and extras.

**Scope**:
- Keep the `all` extra aligned with documented installable feature extras.
- Add a low-noise check for current docs/examples that rejects stale
  `pip install chirp[...]` guidance outside historical directories.
- Decide whether old RFC/release pages get current-guidance callouts or remain
  untouched as historical artifacts.
- Keep SQLite guidance clear: stdlib `sqlite3` plus `anyio`, no `data` extra.

**Required proof**:
- Add a focused optional-extra guardrail test, then run that test. Suggested
  path: `tests/test_optional_extras.py`.
- Targeted docs search for stale install commands outside historical paths.
- Scaffold tests when scaffold install guidance changes.

**Collateral**: Installation docs, data docs, example README files, CLI error
messages, and changelog for user-facing install behavior.

### 4. General Optional Extension Readiness Pattern

**Goal**: Apply the installed/configured/runtime-ready distinction beyond
ChirpUI only where an extension has a real runtime boundary.

**Candidate surfaces**:
- `markdown`: filter registration and missing `patitas` guidance.
- `ai`: provider dependency guidance and streaming-helper examples.
- `redis`/sessions/rate limit: backend package presence and middleware wiring.
- `data-pg`: PostgreSQL driver presence and connection/config diagnostics.

**Scope**:
- Inventory optional extras and classify each as import-only, adapter-wired, or
  middleware/runtime-wired.
- For adapter-wired surfaces, define a tiny capability probe and install
  message pattern.
- Add `app.check()` rules only when static evidence exists and false positives
  are low.

**Required proof**:
- Inventory table in this plan or a follow-up docs artifact.
- Focused tests for each accepted adapter readiness probe.
- No new core dependencies.

**Collateral**: Public optional-extra docs, source import errors, examples, and
steward notes for each touched domain.

## Not Now

- Moving chirp-ui into core dependencies.
- Rewriting plugin protocols or extension registration.
- Emitting noisy `app.check()` warnings for packages that are merely installed.
- Changing top-level exports or adapter public APIs without separate steward
  review.
- Cleaning historical release notes as part of implementation PRs unless the
  release/history wording itself is the requested artifact.

## Acceptance Criteria

- Every optional adapter with runtime wiring has one documented blessed setup
  path and a test that protects its missing/incomplete dependency message.
- Current docs/examples/scaffolds no longer teach stale package names for
  installable features.
- Optional-extension contract categories have documented severity and fix
  guidance.
- No PR in this epic makes an optional dependency mandatory.
- Each implementation PR includes steward notes naming accepted findings,
  deferred findings, proof, and collateral updates.

## Steward Routing

| Surface | Primary Steward | Required Peers |
| --- | --- | --- |
| ChirpUI adapter | `src/chirp/ext/AGENTS.md` | contracts, examples, docs/site, tests |
| Contract categories | `src/chirp/contracts/AGENTS.md` | terminal/server, docs/site, tests |
| Install guidance | `docs/AGENTS.md`, `site/AGENTS.md` | public API, CLI, examples, data/AI/security/cache |
| Optional extras | nearest package steward | public API, tests, changelog |

## Parity Matrix

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ChirpUI runtime readiness | CLI only if scaffold guidance changes | `use_chirp_ui(app)` capability probes | htmx/OOB/page-shell assets remain adapter-owned | no new core types | setup and category docs | ChirpUI examples | boundary, filters, contract checks |
| Optional install guidance | CLI errors/scaffold deps | import errors | no wire change | optional-dependency metadata | install and feature docs | README/docstrings | optional-extra guardrails |
| Category reference | `chirp check` output docs | `override_contract_severity()` examples | no wire change | category strings | contract-debugging docs | no example unless illustrative | docs and category existence checks |
| General readiness pattern | no new command by default | per-adapter probes only when useful | middleware/runtime surfaces only where existing | no mandatory deps | optional-extra docs | focused examples only | package-specific tests |

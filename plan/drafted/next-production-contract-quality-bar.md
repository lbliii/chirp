# Plan: Production Contract Quality Bar

**Status**: Ready for next session
**Created**: 2026-05-09
**Source**: PR #125 lessons, `plan/roadmap.md`, `plan/drafted/epic-downstream-product-success.md`
**Goal**: Make Chirp's framework contracts boringly dependable for production-shaped apps.
**Non-goal**: Build downstream products, product schemas, forum workflows, or UI-library features in Chirp core.

## Read This First

Chirp feels strongest when it helps downstream products succeed through
framework contracts, diagnostics, and examples, not by absorbing product
surface area. The next quality bar is to make forms, streaming/SSE, mounted
apps, and free-threaded shared state predictable under production patterns.

Before implementing, read the nearest steward file for every touched domain and
keep changes traceable to one phase below.

## Phase 1: Production Forms And CSRF Confidence

**Status**: Complete on `codex/production-contract-quality-bar`.

**Why**: Forms are the easiest place for app authors to accidentally split
browser fallback, htmx fragments, validation, CSRF, and mounted route contracts.

**Scope**:

- Audit `docs/forms-production.md`, form examples, and current form contract
  tests for drift after PR #125.
- Confirm the baseline stack shows `SessionMiddleware(SessionConfig(...))`
  before `CSRFMiddleware`.
- Strengthen any missing end-to-end proof around repeated fields,
  multi-intent submit buttons, `FormContract`, htmx validation fragments, and
  plain browser fallback.
- Keep automatic HTML mutation for CSRF injection out of core.

**Required proof**:

- `uv run pytest tests/test_form_integration.py tests/contracts/test_forms.py tests/contracts/test_form_routes.py -q`
- `uv run pytest tests/test_csrf.py tests/test_safe_url.py -q`
- Docs/examples update only if the audit finds drift.

**Done when**:

- A product-shaped POST flow can be explained from docs and proven by tests
  without relying on private helpers or response rewriting.

**Completed proof**:

- `csrf_field()` now renders the active `CSRFConfig.field_name` instead of
  always rendering `_csrf_token`.
- `csrf_form` scans accept the configured field name and skip static form
  targets covered by `CSRFConfig.exempt_paths`.
- Focused and full verification passed:
  `tests/test_form_integration.py tests/contracts/test_forms.py tests/contracts/test_form_routes.py`,
  `tests/test_csrf.py tests/test_safe_url.py`, `tests/docs`, `ruff`, `ty`, and
  the full non-slow pytest suite.

## Phase 2: Streaming, Suspense, And SSE Reliability

**Status**: Complete on `codex/production-contract-quality-bar`.

**Why**: Streaming bugs are often visible only after navigation or reconnect,
and product dashboards need clear ownership boundaries for durable replay.

**Scope**:

- Keep `Stream`, `Suspense`, and `EventStream` guidance distinct.
- Confirm `DeferredCache` behavior after PR feedback: closing one shared
  deferred must not poison other consumers.
- Audit SSE docs and examples for wording that implies Chirp owns durable
  replay queues. Products own durable cursors; Chirp should make
  `Last-Event-ID` patterns easy to prove.
- Advance `plan/drafted/shell-oob-sse-browser-smoke.md` only if a browser
  harness exists or can be added narrowly.

**Required proof**:

- `uv run pytest tests/test_cache.py tests/test_concurrency/test_deferred_cache_contention.py -q`
- `uv run pytest tests/test_suspense.py tests/test_sse_integration.py tests/contracts/test_sse.py -q`
- Browser smoke proof only when touching live DOM shell/SSE behavior.

**Done when**:

- Reconnect, per-event failure, Suspense cache reuse, and close semantics are
  documented or tested with no ambiguous ownership between Chirp and product
  code.

**Completed proof**:

- Confirmed `DeferredCache.close()` behavior is already covered by the
  no-poisoning regression and contention tests.
- Published SSE docs now describe `Last-Event-ID`, `SSEEvent(id=...)`, and the
  product-owned durable cursor boundary.
- Added docs guard coverage so source and site docs keep naming reconnect
  ownership explicitly.
- Focused verification passed:
  `tests/test_cache.py tests/test_concurrency/test_deferred_cache_contention.py`,
  `tests/test_suspense.py tests/test_sse_integration.py tests/contracts/test_sse.py`,
  and `tests/docs`.

## Phase 3: Mounted Apps, URL Scope, And Route Contracts

**Status**: Complete on `codex/production-contract-quality-bar`.

**Why**: Downstream products use mounted filesystems, tenant/base-path URLs,
and generated wrappers. Route reversal, request URL scope, route explorer, and
`app.check()` must agree.

**Scope**:

- Audit `RequestUrlScope`, `Request.scoped_url(...)`, and request-bound
  `Request.url_for(...)` against mounted apps and background/no-request
  renders.
- Preserve deterministic app-root `app.url_for(...)`.
- Confirm route explorer and terminal contract output show the same mounted
  route/form state.
- Keep `examples/chirpui/forum_shell` as a regression fixture, not a product
  scaffold.

**Required proof**:

- `uv run pytest tests/test_url_for.py tests/test_request.py tests/test_decorators.py -q`
- `uv run pytest tests/test_route_explorer.py tests/contracts/test_forms.py -q`
- `uv run pytest examples/chirpui/forum_shell -q --tb=short --timeout=60 -m "not slow"`

**Done when**:

- Tenant-like URL generation and mounted-page contract reporting are explicit,
  request-local, and proven without rendered-HTML URL rewriting.

**Completed proof**:

- Added mounted child-app coverage showing request-local `url_for(...)` scopes
  both regular links and htmx URLs while app-root `app.url_for(...)` stays
  deterministic.
- Confirmed the debug route explorer endpoint exposes real mounted page form
  contracts, including the form type, target block, and serialized contract
  marker.
- Focused verification passed:
  `tests/test_url_for.py tests/test_request.py tests/test_decorators.py`,
  `tests/test_route_explorer.py tests/contracts/test_forms.py`, and
  `examples/chirpui/forum_shell`.

## Phase 4: Free-Threaded Shared State

**Status**: Complete on `codex/production-contract-quality-bar`.

**Why**: Chirp targets Python 3.14t. Shared registries, caches, event buses,
middleware state, and context publication need locks or clear lifecycle
boundaries.

**Scope**:

- Audit recently touched shared state: cache inflight maps, reactive buses,
  route/runtime registries, middleware state, and context variables.
- Prefer frozen/slotted data structures and explicit locks.
- Add focused contention tests where a bug would corrupt app state, leak values
  across requests, or poison other consumers.
- Do not broaden into a generic performance project unless a benchmark is part
  of the acceptance criteria.

**Required proof**:

- `uv run pytest tests/test_concurrency -q`
- Focused domain tests for any changed shared-state package.
- `uv run ty check src/chirp/`

**Done when**:

- Every changed shared mutable structure has an explicit synchronization or
  lifecycle argument, plus a test that would have caught the risky interleaving.

**Completed proof**:

- Closed a lifecycle gap where `freeze_params(...)` and `freeze_exclude(...)`
  could mutate freeze setup state after runtime publication.
- Added concurrency coverage showing simultaneous `app.freeze()` calls publish
  one runtime and run setup domain registration once.
- Added threaded post-freeze mutation coverage for freeze setup APIs.
- Focused verification passed:
  `tests/test_concurrency`, `tests/test_freeze_static.py`,
  `tests/test_app/test_freeze.py`, and `ty check src/chirp/`.

## Phase 5: Diagnostics, Docs, And Fixtures

**Status**: Complete on `codex/production-contract-quality-bar`.

**Why**: Production dependability needs failure messages and examples that
teach the safe path before users inspect internals.

**Scope**:

- Ensure diagnostics name the route, template, block, selector, middleware,
  config flag, or import string that must change.
- Keep examples executable and narrow; examples should prove framework
  contracts, not become product templates.
- Update contract category docs when checks, severities, or terminal output
  change.
- Keep roadmap status current when a phase lands or is explicitly deferred.

**Required proof**:

- `uv run pytest tests/docs -q`
- `uv run pytest tests/docs/test_site_link_drift.py -q`
- Relevant example tests for any README or fixture claim.

**Done when**:

- A future agent can read docs, run a targeted command, and understand whether
  behavior is shipped, planned, or intentionally not now.

**Completed proof**:

- Mapped recently added public contract categories to specific terminal concern
  groups instead of the generic `Other` bucket.
- Updated public contract debugging guidance to describe concrete fix targets:
  route, template, block, selector, middleware, config flag, import string, or
  registration.
- Added docs guards so the contract guidance keeps naming those fix targets and
  recent categories.
- Focused verification passed:
  `tests/test_terminal_checks.py`, `tests/docs`, and
  `tests/docs/test_site_link_drift.py`.

## Suggested Next-Session Order

1. Start with Phase 1 unless CI/review feedback points elsewhere.
2. Keep one phase per commit.
3. After each phase, update this file with `Status: complete`, `deferred`, or
   the exact remaining blocker.
4. Run full CI-equivalent checks before opening or updating a PR:

```text
uv run ruff check .
uv run ruff format . --check
uv run ty check src/chirp/
uv run pytest -q --tb=short --timeout=60 -m "not slow"
```

## Not Now

- A full forum or downstream product inside this repository.
- Generic app-builder abstractions.
- Automatic rendered HTML mutation for URLs or CSRF.
- Core dependency on `chirp-ui`.
- Contract severity promotions without a focused maintainer review.
- Browser harness expansion beyond one deterministic shell/OOB/SSE smoke.

# Chirp Roadmap

Status: active roadmap for 0.6.x maturity work.

Chirp's north star is unchanged: Python developers should be able to build
hypermedia-native applications with server-rendered HTML, typed return values,
startup contracts, streaming, and no JavaScript build pipeline. The work below
turns that thesis into something an outside developer can trust.

## Current Health

- Core tests pass independently with `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"`.
- Lint and format are clean with `uv run ruff check .` and `uv run ruff format . --check`.
- Type checking exits successfully; known warnings are tracked in `pyproject.toml`.
- Examples are treated as executable documentation and must stay under test.
- Contract checks are the framework's flagship reliability feature, not an optional nicety.

Steward check-in on 2026-05-01:

- `uv run ruff check .` and `uv run ruff format . --check` passed.
- `uv run ty check src/chirp/` passed.
- `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` passed.
- `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` passed.
- `uv run pytest tests/contracts -q --tb=short --timeout=60` passed.
- `uv run pytest tests/test_concurrency -q --tb=short --timeout=60` passed.
- `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output /tmp/chirp-core-steward-smoke.json` passed.

## Phase 0: Make Main Boring

Goal: `main` should feel calm. A contributor should be able to run the standard checks and
believe the result.

Status: current release-gate checks are green as of the 2026-05-01 steward check-in. Keep this
phase active as a regression guard; any failing example, noisy warning, or free-threaded warning
should be treated as release-blocking until classified.

Deliverables:

- Keep `tests/` and `examples/` green under CI-equivalent commands.
- Add `app.check()` coverage to examples as they are hardened.
- Remove or classify noisy warnings from tests and examples.
- Keep examples compatible with current Kida template rules.
- Fix free-threaded warnings before they become intermittent failures.

Acceptance:

- `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` passes.
- `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` passes.
- Example contract checks fail on errors, not on known warnings.
- No unhandled thread exceptions in concurrency tests.

## Phase 1: Make Contracts The Flagship

Goal: `app.check()` should be the thing people remember. If an app starts clean, its
hypermedia surface should be coherent.

Status: grouped terminal output by concern and elapsed timing diagnostics are implemented and
covered by `tests/test_terminal_checks.py`. Remaining work should focus on preserving message
actionability, adding checks only for user-visible failure modes, and keeping debug startup fast.

Deliverables:

- Group contract output by concern: routing, templates, htmx, OOB/Suspense/SSE,
  accessibility, forms, production safety.
- Add timing diagnostics for large apps.
- Expand checks only when they catch user-visible failure modes.
- Keep severity changes deliberate; use `override_contract_severity()` as the escape valve.
- Document broken-example -> check-output -> fixed-example workflows.

Acceptance:

- Every new hypermedia feature ships with an end-to-end contract test.
- Contract messages name the template, route, block, and next action.
- Contract checks remain fast enough for debug startup.

## Phase 2: Free-Threaded Reliability

Goal: the Python 3.14t claim should be earned, not ornamental.

Deliverables:

- Audit runtime shared state: registries, buses, caches, context, middleware, and test helpers.
- Prefer frozen dataclasses and copy-on-write values.
- Protect intentional mutable state with `threading.Lock` or loop-safe handoff.
- Run concurrency stress tests repeatedly in CI or scheduled jobs.
- Document the locking story for every new shared runtime primitive.

Acceptance:

- Concurrency tests have no unhandled thread warnings.
- `ReactiveBus`, cache backends, OOB registry, and context isolation have stress coverage.
- PRs touching shared state explain the synchronization model.

## Phase 3: Defensible Performance

Goal: Chirp should be fast for the workloads that match its thesis, with benchmark claims
that survive scrutiny.

Deliverables:

- Version benchmark environments: Python build, OS, CPU, Pounce version, worker mode.
- Add workloads for template render, fragment render, OOB serialization, Suspense first
  chunk, SSE fanout, and filesystem route dispatch. Initial in-process regression suite lives in
  `python -m benchmarks.core` and writes JSON artifacts with environment metadata.
- Track internal regression thresholds separately from Flask/FastAPI comparisons.
- Keep the sync fast path narrow, measured, and documented.

Acceptance:

- Benchmarks produce reproducible JSON artifacts.
- Hot-path regressions are caught before release.
- Public claims avoid synthetic-overreach language.

## Phase 4: Public API Discipline

Goal: the framework should feel smaller than it is.

Deliverables:

- Mark public surfaces as stable, provisional, or internal.
- Keep `chirp.__all__` intentional and tested.
- Revisit `AppConfig` breadth; group future expansion behind existing fields or sub-configs
  before adding new top-level fields.
- Clarify optional extras: `forms`, `sessions`, `auth`, `markdown`, `ui`, `redis`,
  `data-pg`, `ai`, `config`, `benchmark`.
- Define deprecation policy before 0.5: warning type, minimum duration, docs location.

Acceptance:

- A new user can learn the core API from `from chirp import ...` plus README.
- Public API changes require changelog fragments and migration notes.
- No new return type, config field, or runtime dependency lands without design review.
- Top-level exports have a tested stability classification and are documented in `docs/public-api.md`.

## Phase 5: PBP Forum Proof App

Goal: build a real product that proves Chirp's model under application pressure.

The play-by-post forum is not a side quest. It is the first serious downstream app and the
best way to expose missing ergonomics.

Sprint order:

1. Auth and accounts: registration, login, sessions, password reset, current-user context.
2. Core forum: boards, threads, posts, markdown rendering, pagination.
3. Hypermedia UX: htmx fragments, OOB unread counts, validation errors, mutation results.
4. Realtime: thread-scoped SSE, notifications, unread tracking, presence.
5. PBP features: characters, post-as-character, profiles, theming, moderation.

Rules:

- Product code first unless a framework abstraction is clearly reusable.
- Every sprint ships a playable slice.
- Framework changes discovered by the product get their own focused PR.
- The forum should run without npm, without an SPA, and without a parallel JSON API.

## Release Gates

Before a 0.5.x release:

- `uv run ruff check .`
- `uv run ruff format . --check`
- `uv run ty check src/chirp/`
- `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"`
- `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"`
- Benchmark smoke run for core workloads
- Changelog fragments compiled or verified

## Near-Term Queue

1. Finish Phase 0 example hardening and warning triage.
2. Add grouped contract output and timing diagnostics.
3. Finish the ReactiveBus free-threaded delivery audit.
4. Extend `benchmarks.core` with release thresholds after collecting stable local baselines.
5. Tighten deprecation policy wording before the next release.
6. Start the PBP forum Sprint 0 schema/routing RFC.

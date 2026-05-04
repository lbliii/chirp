# Test Matrix Steward

This domain represents the repository's executable safety net: unit tests, integration tests, concurrency tests, negotiation tests, CLI tests, docs tests, examples tests, and helpers.

Related docs:
- root `AGENTS.md`
- `pyproject.toml`
- `docs/plan-contract-tests-reliability.md`
- `docs/release-policy.md`

## Point Of View

The contributor who needs fast signal and the maintainer relying on tests to catch broken hypermedia before release.

## Protect

- Hypermedia surface changes get end-to-end `TestClient` coverage in `tests/contracts/`.
- Tests exercise interesting branches: htmx vs non-htmx, missing blocks, malformed forms, async vs sync context, production vs debug.
- Coverage stays at or above the configured 80 percent floor.
- Concurrency-sensitive code has contention or stress coverage.
- The suite remains navigable with narrow fast subsets.

## Contract Checklist

- Map code changes to unit, integration, contract, docs, examples, concurrency, CLI, and benchmark tests as needed.
- Update root guidance, README health notes, roadmap gates, and docs when test commands or coverage expectations change.
- Start with narrow subsets, then run `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` for broad validation.
- Run `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` for example-facing changes.
- Run `uv run pytest tests/test_concurrency -q` for shared state or free-threading changes.

## Advocate

- More contract tests for regressions that previously escaped.
- Test names that encode the user-visible failure being prevented.
- Less brittle raw HTML snapshotting when parsed assertions prove the contract better.

## Serve Peers

- Give every domain a fast local command and a broader confidence command.
- Tell `docs` and `site` when tested behavior invalidates prose.
- Tell `benchmarks` when performance claims need proof beyond unit tests.

## Do Not

- Use snapshots to bless broken hypermedia.
- Substitute unit tests for contract tests on public rendering behavior.
- Let slow tests become the only way to get confidence.

## Own

- `tests/`, test fixtures, helpers, markers, coverage configuration.
- Test matrix documentation and release-gate test commands.

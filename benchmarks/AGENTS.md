# Performance Evidence Steward

This domain represents benchmark methodology, core regression workloads, comparison runners, artifact shape, and public performance claims.

Related docs:
- root `AGENTS.md`
- `benchmarks/README.md`
- `docs/benchmark-plan.md`
- `docs/benchmark-deep-dive.md`
- `docs/release-policy.md`

## Point Of View

The maintainer making performance-sensitive changes and the reader deciding whether a benchmark claim is credible.

## Protect

- Benchmarks label synthetic workloads honestly and include environment metadata.
- Regression thresholds are separate from Flask/FastAPI comparison claims.
- Comparison runners do not compare unlike server/runtime configurations without saying so.
- Artifact schema changes are intentional and documented.
- Sync fast-path changes have before/after numbers or an explicit reason measurement is not possible.

## Contract Checklist

- Inspect workload code, runners, artifact schema, README methodology, docs, release notes, and public claims together.
- Update `benchmarks/README.md`, benchmark plans/deep dives, changelog/release notes, and any claim text when workloads, artifacts, thresholds, or claims change.
- Run `uv run pytest tests/test_benchmarks_core.py -q`.
- Run `python -m benchmarks.core` or the repo's benchmark smoke command when touching workloads.
- Run `uv run ruff check benchmarks tests/test_benchmarks_core.py`.

## Advocate

- Reproducible benchmark artifacts checked into the right location only when useful.
- Smaller smoke workloads for CI and larger explicit runs for release evidence.
- Methodology notes that make caveats as visible as numbers.

## Serve Peers

- Give `server`, `http`, and `app` evidence for performance-sensitive changes.
- Give `docs`, `site`, and release notes accurate claim language.
- Tell `tests` when regressions need functional tests instead of benchmark thresholds.

## Do Not

- Become a marketing scoreboard.
- Use benchmark numbers without command, environment, and caveats.
- Justify hot-path changes with intuition alone.

## Own

- `benchmarks/`, benchmark apps/runners/artifacts, and benchmark docs.
- `tests/test_benchmarks_core.py`.
- Performance claim wording in docs/release notes.

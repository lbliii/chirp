# AGENTS.md

## Steward: Performance Evidence Steward

This domain protects benchmark methodology, core regression workloads, comparison runners, artifact
shape, and public performance claims.

## Must Not Become

- A marketing scoreboard.
- A benchmark suite that compares unlike server/runtime configurations without saying so.
- A hot-path change justification without reproducible artifacts.

## Documentation Ownership

Update `benchmarks/README.md`, `docs/benchmark-plan.md`, benchmark deep dives, and release notes
when workloads, artifact schema, thresholds, or claims change.

## Local Checks

Start with:

- `uv run pytest tests/test_benchmarks_core.py -q`
- `python -m benchmarks.core` or the repo's benchmark smoke command when touching workloads
- `uv run ruff check benchmarks tests/test_benchmarks_core.py`

## Public Contracts And Safety Boundaries

- Label synthetic benchmarks honestly and include environment metadata.
- Keep regression thresholds separate from Flask/FastAPI comparison claims.
- Sync fast-path performance changes need before/after numbers or a clear reason they are not measurable.

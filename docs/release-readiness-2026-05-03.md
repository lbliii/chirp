# Release Readiness Check — 2026-05-03

This note records the maturity-pass release gate run for Chirp `0.6.0`. It was
rerun after the public-surface, `AppConfig`, and stable error-message audit
changes. It is release evidence, not a tag or publication record.

## Result

All release gates from `docs/release-policy.md` passed on 2026-05-03. The final
rerun completed at benchmark timestamp `2026-05-03T16:09:59.745260+00:00`.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 665 files already formatted |
| `uv run ty check src/chirp/` | Pass | No type findings |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | 4 skips for missing optional `argon2-cffi` |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Example suite clean |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Artifact written to `.benchmarks/core-latest.json` |
| `uv run towncrier build --version 0.6.0 --draft` | Pass | Draft only; changelog was not compiled |
| `uv build` | Pass | Built sdist and wheel |

## Benchmark Snapshot

Environment: CPython 3.14.2, free-threaded, Darwin arm64.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 7.291 | 10.958 |
| Fragment render | 7.375 | 13.000 |
| OOB serialization | 24.458 | 25.041 |
| Suspense first chunk | 16.792 | 21.792 |
| SSE fanout | 5.375 | 7.084 |
| Filesystem route dispatch | 0.625 | 0.750 |

## Residual Notes

- The checkout was clean except for pre-existing untracked `site/assets/`.
- The alpha classifier and `0.x` version remain accurate. This check supports a
  release candidate, not a 1.0 claim.
- Build artifacts are generated outside this package directory by `uv build`
  according to the workspace layout.

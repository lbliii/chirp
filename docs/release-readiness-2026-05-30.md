# Release Readiness Check - 2026-05-30

This note records the release gate run for Chirp `0.7.1` on
`codex/next-release-roadmap`. It is release evidence, not a tag or publication
record.

## Result

All release gates from `docs/release-policy.md` passed on 2026-05-30. The
benchmark artifact was generated at `2026-05-30T13:03:23.289316+00:00`.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 689 files already formatted |
| `uv run ty check src/chirp/` | Pass | No type findings |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | 4 skips for missing optional `argon2-cffi` |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Example suite clean |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Artifact written to `.benchmarks/core-latest.json` |
| `uv run towncrier build --version 0.7.1 --draft` | Pass | Draft contained Changed and Fixed sections |
| `uv build` | Pass | Built sdist and wheel under `dist/` |

## Benchmark Snapshot

Environment: CPython 3.14.2, free-threaded, Darwin arm64.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 12.958 | 62.875 |
| Fragment render | 10.750 | 12.458 |
| OOB serialization | 43.041 | 91.458 |
| Suspense first chunk | 23.042 | 129.625 |
| SSE fanout | 7.958 | 56.125 |
| Filesystem route dispatch | 0.958 | 1.167 |

## Release Artifacts

- Package version bumped to `0.7.1`.
- `CHANGELOG.md` includes the compiled `0.7.1` release entry.
- `site/content/releases/0.7.1.md` is present for the GitHub release target.
- `dist/bengal_chirp-0.7.1.tar.gz` and
  `dist/bengal_chirp-0.7.1-py3-none-any.whl` were built locally.

## Residual Notes

- No tag, GitHub release, PyPI publish, or generated `site/public` output was
  created by this readiness pass.
- The next larger roadmap item remains the Fragment/SSE example audit and
  browser smoke; it is not part of this patch release.

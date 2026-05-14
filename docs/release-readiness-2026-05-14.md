# Release Readiness Check — 2026-05-14

This note records the release gate rerun for Chirp `0.7.0` after pulling
`origin/main` to `feee030`. It is release evidence, not a tag or publication
record.

## Result

All release gates from `docs/release-policy.md` passed on 2026-05-14. The
benchmark artifact was generated at `2026-05-14T15:41:03.785119+00:00`.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 684 files already formatted |
| `uv run ty check src/chirp/` | Pass | No type findings |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | 4 skips for missing optional `argon2-cffi` |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Example suite clean |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Artifact written to `.benchmarks/core-latest.json` |
| `uv run towncrier build --version 0.7.0 --draft` | Pass | Draft contained the post-prep Changed and Fixed fragments |
| `uv build` | Pass | Built sdist and wheel under `dist/` |

## Benchmark Snapshot

Environment: CPython 3.14.2, free-threaded, Darwin arm64.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 11.042 | 138.958 |
| Fragment render | 11.042 | 50.084 |
| OOB serialization | 39.458 | 196.333 |
| Suspense first chunk | 25.625 | 114.250 |
| SSE fanout | 7.750 | 11.666 |
| Filesystem route dispatch | 2.250 | 9.875 |

## Release Artifacts

- Package version remains `0.7.0`; PyPI and GitHub latest release are `0.6.0`.
- Optional `chirp-ui` dependency floor is `>=0.9.0` in package metadata,
  development example dependencies, and new scaffolded projects.
- `CHANGELOG.md` includes the compiled `0.7.0` release entry plus the
  post-prep debug reload and `chirp-ui>=0.9.0` updates.
- `site/content/releases/0.7.0.md` is present for the GitHub release target.
- `dist/bengal_chirp-0.7.0.tar.gz` and
  `dist/bengal_chirp-0.7.0-py3-none-any.whl` were built locally.

## Residual Notes

- The release fragments for debug reload and the `chirp-ui>=0.9.0` floor were
  folded into the existing `0.7.0` release collateral because `0.7.0` has not
  been tagged or published.
- No tag, GitHub release, PyPI publish, or generated `site/public` output was
  created by this readiness pass.

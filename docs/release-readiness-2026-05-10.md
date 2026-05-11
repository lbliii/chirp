# Release Readiness Check — 2026-05-10

This note records the release gate run for Chirp `0.7.0` after pulling
`origin/main` to `bcc6a74`. It is release evidence, not a tag or publication
record.

## Result

All release gates from `docs/release-policy.md` passed on 2026-05-10. The
benchmark artifact was generated at `2026-05-10T23:55:09.853752+00:00`.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 683 files already formatted |
| `uv run ty check src/chirp/` | Pass | No type findings |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | 4 skips for missing optional `argon2-cffi` |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Example suite clean |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Artifact written to `.benchmarks/core-latest.json` |
| `uv run towncrier build --version 0.7.0 --draft` | Pass | Draft included Added, Changed, Fixed, and Security sections |
| `uv run towncrier build --version 0.7.0 --yes` | Pass | Compiled fragments into `CHANGELOG.md` |
| `uv build` | Pass | Built sdist and wheel under `dist/` |

## Benchmark Snapshot

Environment: CPython 3.14.2, free-threaded, Darwin arm64.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 10.458 | 15.833 |
| Fragment render | 11.000 | 14.875 |
| OOB serialization | 36.250 | 116.125 |
| Suspense first chunk | 23.209 | 137.583 |
| SSE fanout | 8.083 | 55.750 |
| Filesystem route dispatch | 0.958 | 1.041 |

## Release Artifacts

- Package version bumped to `0.7.0`.
- Optional `chirp-ui` dependency floor bumped to `>=0.8.0` after verifying
  GitHub release `lbliii/chirp-ui@v0.8.0`.
- `CHANGELOG.md` includes the compiled `0.7.0` release entry.
- `site/content/releases/0.7.0.md` is present for the GitHub release target.
- `dist/bengal_chirp-0.7.0.tar.gz` and
  `dist/bengal_chirp-0.7.0-py3-none-any.whl` were built locally.

## Residual Notes

- The compiled changelog consumed all release fragments under `changelog.d/`.
- Towncrier initially ignored fragments named `.bugfix.md`; those entries were
  corrected to the configured `.fixed.md` type before compilation.

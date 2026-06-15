# Release Readiness Check - 2026-06-15

This note records the release gate run for Chirp `0.8.0` on `lbliii/cut-release`.
It is release evidence, not a tag or publication record.

## Result

All release gates from `docs/release-policy.md` passed on 2026-06-15. The
benchmark artifact was generated at `2026-06-15T18:59:16.434511+00:00`.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 801 files already formatted |
| `uv run ty check src/chirp/` | Pass | Exit 0; 5 baseline `Mapping.get` override warnings (informational, non-blocking) |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Skips: optional `argon2-cffi`, no `CHIRP_TEST_PG_DSN` PostgreSQL round-trip |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | One skip: `playwright` not installed (lucky_cat browser smoke) |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Artifact written to `.benchmarks/core-latest.json` |
| `uv run towncrier build --version 0.8.0 --draft` | Pass | Draft contained Added, Changed, Fixed, and Security sections |
| `uv build` | Pass | Built sdist and wheel under `dist/` |

`scripts/check_changelog_fragments.py` and `test_public_api_docs.py` (public-API
and AppConfig config-guide drift guards) also passed before the changelog was
compiled.

## Benchmark Snapshot

Environment: CPython 3.14.3, GIL-enabled (not free-threaded for this run),
Darwin arm64. Synthetic core workloads — release evidence, not a marketing
claim.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 8.791 | 66.541 |
| Fragment render | 7.042 | 39.125 |
| OOB serialization | 28.417 | 181.333 |
| Suspense first chunk | 114.458 | 362.208 |
| SSE fanout | 5.209 | 8.291 |
| Filesystem route dispatch | 1.542 | 4.167 |

## Release Artifacts

- Package version bumped to `0.8.0` (and the two towncrier poe tasks).
- `CHANGELOG.md` includes the compiled `0.8.0` release entry (32 added, 3
  changed, 11 fixed, 6 security; 52 fragments consumed from `changelog.d/`).
- `site/content/releases/0.8.0.md` is present for the GitHub release target.
- `dist/bengal_chirp-0.8.0.tar.gz` and
  `dist/bengal_chirp-0.8.0-py3-none-any.whl` were built locally.

## Notable Changes Requiring Migration

`0.8.0` adjusts several stable defaults. Each carries a migration note in
`CHANGELOG.md` and the site release notes:

- Default CSP drops `'unsafe-inline'` from `script-src` (per-request nonce now
  required for framework inline scripts).
- `EventStream` defaults to same-origin (no implicit wildcard CORS).
- `max_upload_size` re-scoped to multipart-total; new `max_request_body_size`
  for the general envelope; dead `max_content_length` removed.
- SQLite `DatabaseConfig.pool_size` is now load-bearing (WAL connection pool).

## Residual Notes

- No tag, GitHub release, PyPI publish, or generated `site/public` output was
  created by this readiness pass.
- The dependency floor for `bengal-pounce` is raised to `>=0.8.0`; `kida-templates`
  (`>=0.9.0`) and the optional `chirp-ui` (`>=0.9.0`) floors are unchanged.
- The Lucky Cat demo `Dockerfile` installs chirp from `git@${CHIRP_REF}`; the
  planned switch to the PyPI `bengal-chirp` package is a post-release follow-up.

# Release Readiness Check - 2026-07-08

This note records the release gate run for Chirp `0.10.0` on local `main` at
`1b0eeba5`, plus the release-preparation and issue #618 changes in the working
tree. It is release evidence, not a tag or publication record.

## Result

The code, changelog, package, benchmark, source-site, and downstream
compatibility gates pass. Repository Actions secret `FURATENA_CANARY_TOKEN`
was configured at `2026-07-09T01:53:26Z`, allowing GitHub Actions to repeat the
locally successful advisory canary during publication.

| Gate | Result | Notes |
|------|--------|-------|
| `uv run ruff check .` | Pass | No lint findings |
| `uv run ruff format . --check` | Pass | 1,099 files formatted |
| `uv run ty check src/chirp/` | Pass | Two pre-existing tuple-unpacking diagnostics in `tools/registry.py` were narrowed with structural tuple patterns; focused tool tests passed afterward |
| `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Full framework suite passed in 361.5 seconds; optional browser, protocol-client, PostgreSQL, Redis, password, and provider lanes skipped when their dependencies or environment were absent |
| `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` | Pass | Full example suite passed in 517 seconds; six Playwright browser smokes skipped because Playwright is not installed locally |
| `uv run pytest tests/test_sessions.py tests/test_csrf.py tests/test_streamed_render_context.py tests/contracts/test_sse_auth.py -q --tb=short --timeout=60` | Pass | Focused #618 proof covers anonymous no-write behavior, existing-cookie refresh, timeout metadata, nested mutation, regeneration, CSRF, streaming, and SSE |
| `uv run pytest tests/test_tools.py tests/test_tools/ tests/contracts/test_surface_diff_tool.py -q --tb=short --timeout=60` | Pass | 83 focused tool registry, approval, schema, handler, and surface-diff tests passed after the typing fix |
| `uv run python -m benchmarks.core --iterations 250 --route-count 100 --output .benchmarks/core-latest.json` | Pass | Versioned `0.10.0` artifact written at `2026-07-09T01:33:24.373597+00:00` |
| `uv run towncrier build --version 0.10.0 --draft` | Pass | Draft contained Added, Changed, and Fixed sections, including #618 |
| `uv run towncrier build --version 0.10.0 --yes` | Pass | Compiled 16 fragments into `CHANGELOG.md` |
| `uv build --out-dir /tmp/chirp-release-assessment-0.10.0-final` | Pass | Built the final `0.10.0` sdist and universal wheel after all code changes |
| `./scripts/bengal-site build --environment production` | Pass | Built 727 pages; generated release page contains the `Chirp 0.10.0` title and cacheable-session section |
| Pinned Furatena compatibility slice | Pass | Installed locked dependencies at `da584bf9fe19ec1376fdc0b23c7fb1b657b026b8`, force-installed the final `0.10.0` wheel, verified site-packages provenance, and passed all 11 canary tests |

The production Bengal build completed successfully but retained site-wide
advisory health output: Lunr fell back to runtime indexing, generated local
asset references were reported, and 362 generated API `.txt` links were marked
broken. The new `site/content/releases/0.10.0.md` page rendered successfully and
was not named by those findings. Generated `site/public/` output remains
untracked and is not release source.

## Benchmark Snapshot

Environment: CPython 3.14.2 free-threaded on Darwin arm64. These are synthetic
internal regression workloads, not production performance claims.

| Workload | p50 us | p99 us |
|----------|--------|--------|
| Template render | 26.917 | 39.875 |
| Fragment render | 8.083 | 8.666 |
| OOB serialization | 33.458 | 184.375 |
| Suspense first chunk | 185.291 | 2,893.583 |
| SSE fanout | 13.042 | 42.917 |
| Filesystem route dispatch | 0.625 | 0.792 |

The same-runner pull-request benchmark gate also passed for the latest merged
benchmark change before this release preparation.

## Release Artifacts

- Package and towncrier task versions are `0.10.0`.
- New scaffolds require `bengal-chirp>=0.10.0`.
- `CHANGELOG.md` contains the compiled `0.10.0` release entry.
- `site/content/releases/0.10.0.md` contains the source release page.
- `/tmp/chirp-release-assessment-0.10.0-final/` contains the final built sdist
  and wheel.

## Issue #618 Proof

`SessionMiddleware` now skips persistence only when all three conditions hold:
there was no incoming session cookie, the final session is empty, and explicit
regeneration was not requested. Regeneration intent uses mutable request-local
context state so synchronous handler context copies preserve the signal without
introducing global shared state.

Existing-cookie sliding refresh, timeout metadata, CSRF token creation, nested
mutation, tampered-cookie recovery, login/logout, and explicit regeneration
continue through the store's save path. The change adds no public type, config
field, export, dependency, or migration surface.

## Canary Credential And Publication Check

The `0.9.0` advisory Furatena canary failed before checkout because
`FURATENA_CANARY_TOKEN` was not configured. The local GitHub CLI token is a
broad classic token with `repo` scope and was deliberately not copied into CI
because `docs/release-policy.md` requires a fine-grained read-only token.

The exact compatibility slice passes locally against the final wheel. A
fine-grained token was subsequently installed as repository Actions secret
`FURATENA_CANARY_TOKEN`; GitHub exposes its name and update timestamp but not
its value. The publication workflow should repeat the canary and record its
result as advisory release evidence.

No tag, GitHub release, PyPI publication, or generated site output was created
by this readiness pass.

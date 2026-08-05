# Test-duration baseline (#923)

**Status:** Measurement receipt (no execution-strategy change)

**Issue:** [#923](https://github.com/lbliii/chirp/issues/923)

**Parent epic:** [#900](https://github.com/lbliii/chirp/issues/900) → saga [#896](https://github.com/lbliii/chirp/issues/896)

**Revision measured:** `81f0b51aa3133ddcd4584a69d05e6a3a07626786` (`main` at worktree creation)

**Acceptance #923:** n/a — measurement collateral only; no behavioral test.

This document records reproducible commands, environments, node counts, and
timings **before** feedback-tier budgets (#919), xdist rebalancing, or coverage
changes. Numbers are samples, not SLOs.

## Artifacts

| Path | Contents |
| --- | --- |
| `scripts/measure_test_baselines.py` | Local collect / fast / CI-mirror / sequential recipes |
| `docs/receipts/test-duration-baseline-923-collect.json` | Collect-only node counts by family |
| `docs/receipts/test-duration-baseline-923-fast.json` | Preflight / invariants / contracts timings + variance |
| `docs/receipts/test-duration-baseline-923-ci-mirror.json` | Local mirror of the main CI `test` job argv |
| `docs/receipts/test-duration-baseline-923-ci-actions.json` | Five recent successful `main` CI workflow timings |

Re-run locally:

```bash
uv run python scripts/measure_test_baselines.py --profile collect --compact \
  --output docs/receipts/test-duration-baseline-923-collect.json
uv run python scripts/measure_test_baselines.py --profile fast --repeats 3 --compact \
  --output docs/receipts/test-duration-baseline-923-fast.json
uv run python scripts/measure_test_baselines.py --profile ci-mirror --compact \
  --output docs/receipts/test-duration-baseline-923-ci-mirror.json
# Optional / expensive:
uv run python scripts/measure_test_baselines.py --profile sequential --compact \
  --output docs/receipts/test-duration-baseline-923-sequential.json
```

Refresh CI Actions timings with `gh run view <id> --json jobs` (see the
`ci-actions` receipt generator comments in the JSON `source` field).

## Environments

### Local sample host

| Field | Value |
| --- | --- |
| OS | macOS 26.5.2 (Darwin 25.5.0), arm64 |
| CPU | Apple M3 Pro, 11 logical CPUs, 36 GiB RAM |
| Python | CPython **3.14.2 free-threading** (`gil_enabled=False`) via worktree `.venv` |
| Dep profile | `uv sync --group dev` (no Playwright / no live Postgres DSN) |

### CI (GitHub Actions)

| Job | Python | Notes |
| --- | --- | --- |
| `ruff`, `ty`, `test`, `chirp-ui-compat`, `data-pg-gil-gate` | **3.14t** | Main suite sets `PYTHON_GIL=0` |
| `browser-smoke`, `query-interop`, `test-postgres` | **3.14** | Service / browser / protocol dominated |

Workflow source: `.github/workflows/ci.yml`.

## Named command inventory

| Family | Command | Role |
| --- | --- | --- |
| Preflight | `uv run poe preflight` | Lint + format-check + ty + public-API invariants (pre-push) |
| Invariants | `uv run poe test-invariants` | `tests/test_lazy_imports.py` + `tests/test_public_api_docs.py` |
| Contracts | `uv run pytest tests/contracts -q` | Focused hypermedia contract suite |
| CI mirror | `uv run pytest -q --tb=short --timeout=60 -m "not slow" --ignore=examples/chirpui/lucky_cat/test_browser_smoke.py -n 4 --dist loadgroup --cov --cov-report=term` | Exact main `test` job argv |
| Full suite (steward) | `uv run pytest tests -q` | Single authoritative `tests/` entrypoint |
| Default paths | `uv run pytest` / `poe test` | `testpaths = ["tests", "examples"]` |
| Browser smoke | CI `browser-smoke` job | Playwright + Chromium (isolated) |
| PostgreSQL | CI `test-postgres` matrix + `data-pg-gil-gate` | Live Postgres / GIL gate |
| Query interop | CI `query-interop` | Optional H2/H3 clients + nginx |

Markers in use: `slow`, `integration`, `passkeys_e2e`, `issue`.

## Collected node counts (local, revision above)

Verified with both quiet per-file sums and non-quiet
`N tests collected` footers:

| Group | Collected | Notes |
| --- | --- | --- |
| Default paths (`tests` + `examples`) | **6965** | 11 skipped at collection without Playwright / pending Kida API |
| `tests/` only | **6059** | Steward full-suite entrypoint |
| `examples/` only | **906** | |
| CI mirror shape (`-m "not slow"` + lucky_cat browser ignore) | **6963 / 6965** (2 deselected) | Matches main job selection |
| Invariants | **109** | |
| Contracts | **1023** | 3 browser contract modules skip without Playwright |
| Query interop path | **11** | |
| Postgres live paths | **49** | Service-dominated when DSN present |

Epic #900 cited “7,957 collected” for an earlier sequential sample. At this
revision the authoritative collect footer is **6965** (default paths) /
**6059** (`tests/`). Treat 7,957 as historical narrative, not the current
baseline denominator.

## Local timed samples

Host: Apple M3 Pro / CPython 3.14.2t / `uv` worktree venv.

| Command | Samples | Wall time | Notes |
| --- | --- | --- | --- |
| `poe preflight` | 3 | min **2.70s**, median **3.19s**, max **3.61s** | Cheap whole-repo gate |
| Invariants pytest | 3 | min **1.99s**, median **2.07s**, max **2.11s** | Stable |
| `tests/contracts` + `--durations=25` | 1 | **61.4s** wall | One pre-existing local failure in `test_chirp_surface_diff_tool_returns_json_payload` (unrelated to measurement); slowest calls are chirp-ui alpine probe (~1.3s), cache TTL e2e (~1.2s), forum shell baseline roundtrip (~0.9s) |
| CI-mirror (`-n 4 --dist loadgroup --cov`, same argv as CI `test`) | 1 | **257.8s (~4.3m)** wall, exit 0 | 124 skips without Playwright/Postgres/redis; host is faster than `ubuntu-latest` |

Collect-only for the full default tree is ~5–6s wall on this host (not the
execution budget).

### Sequential full suite

Recipe (do not average with CI xdist+coverage):

```bash
uv run pytest tests -q --timeout=60
# optional wider path: uv run pytest -q --timeout=60
```

A fresh sequential wall-clock sample was **not** re-run to completion in this
receipt because it is multi-tens-of-minutes on a laptop while CI-mirror + Actions
already explain the critical path. Epic #900’s prior local figure (~**12m 39s**
sequential) remains the planning anecdote; re-measure with
`--profile sequential` before locking #919 budgets if a current laptop number is
required. On this host the parallel CI-mirror already finishes in ~**4.3m**, so a
sequential `tests/` run should be expected to land well above the Actions
`test` job unless machine class is comparable to GitHub runners.

## CI timings (Actions API)

Five recent successful `main` CI runs (workflow wall and critical-path `test`
job). Source receipt:
`docs/receipts/test-duration-baseline-923-ci-actions.json`.

| Metric | Min | Median | Max | Samples (s) |
| --- | --- | --- | --- | --- |
| Workflow wall | 291 | 376 | 394 | 394, 291, 376, 377, 365 |
| `test` job | 287 | 372 | 378 | 378, 287, 373, 372, 361 |

Representative latest run
([30909653420](https://github.com/lbliii/chirp/actions/runs/30909653420),
sha `81f0b51a`):

| Job | Job wall | Key step |
| --- | --- | --- |
| **test** (critical path) | **378s (~6.3m)** | Tests step **364s**; install ~4s |
| browser-smoke | 163s | Browser smoke 108s; Chromium install 34s |
| PostgreSQL matrix | ~40–54s | Round-trip tests ~7–8s (container/setup dominated) |
| data-pg-gil-gate | 40s | GIL gate pytest ~6s |
| chirp-ui-compat | 34–43s | Shell example smoke dominates after pin |
| query-interop | 24s | Wire proof ~4s (apt/nginx setup dominated) |
| ty / ruff | 13–16s | Check steps ~1s after sync |

Coverage on that `test` job: **87.04%** (floor 80%), python **3.14.6** free-threaded
on `ubuntu-latest`. Quiet pytest + coverage means Actions logs often omit the
classic `N passed in Xs` footer; use job/step timestamps (as here).

### Why ~6 minutes

The required PR critical path is the single `test` job: free-threaded interpreter,
`-n 4 --dist loadgroup`, full default paths minus `slow` and one browser smoke
file, **with coverage**. Sibling jobs finish earlier; workflow wall ≈ `test` job
wall (± cache / queue noise). Variance across five mains: **287–378s** for
`test` (stdev ~38s) — one warmer/faster run at 287s; typical cluster ~360–380s.

### Service-dominated lanes (do not fold into the main budget)

- **browser-smoke:** Playwright/Chromium install + real browser time.
- **test-postgres / data-pg-gil-gate:** container health + TLS fixture + live DB.
- **query-interop:** apt nginx + optional protocol extras.

These prove capability isolation; averaging them into the main pytest budget
would hide the true free-threaded critical path (#919 must keep them separate).

## Planning takeaways for #900 / #919

1. Preflight is already a **~3s** local early signal; it is not the CI critical path.
2. Contracts alone are ~**1 minute** locally — useful focused tier, not a substitute
   for the main job’s ~**6 minutes** of xdist+coverage proof.
3. Node count baseline for strategy work: **~6963** CI-selected nodes, **6059** in
   `tests/`, **1023** contracts, **109** invariants.
4. Worker utilization / fixture cost: contracts durations show multi-second
   chirp-ui and cache e2e calls; CI progress bars stall hardest in the final
   ~15% (roughly 87%→100% took ~2.5 minutes on run 30909653420) — evidence that
   tail imbalance / expensive groups matter more than raw test-body counts.
5. No optimization, deselection, timeout relaxation, or coverage change was made
   in this task.

## Boundaries respected

- No pytest-xdist rebalance, marker changes, or coverage-floor edits.
- No silent skip of capability lanes.
- Receipts prefer measured samples + explicit methodology over speculative targets.

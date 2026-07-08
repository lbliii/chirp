# Chirp Web Framework Benchmarks

Synthetic benchmarks comparing Chirp vs FastHTML vs FastAPI vs Flask vs Starlette vs Litestar on JSON, CPU-bound, SQLite DB, and HTML-rendering workloads. Designed to measure free-threaded Python behavior when using Chirp + Pounce on Python 3.14t.

This directory has two benchmark families:

- `benchmarks.run`: networked framework comparison, useful for Chirp vs FastHTML, FastAPI, Flask, Starlette, and Litestar.
- `benchmarks.core`: in-process Chirp regression workloads, useful for release gates and hot-path tracking.

Pounce 0.7 also ships `pounce bench`, a server-level smoke/comparison command
with generic ASGI workloads (`/hello`, `/json`, `/body`). Treat it as a Pounce
server benchmark, not as a replacement for Chirp's framework-specific JSON,
CPU, DB, template, SSE, and core regression workloads.

## Quick Start

```bash
# Install benchmark dependencies
uv sync --extra benchmark
# or: pip install bengal-chirp[benchmark]

# Run all benchmarks
uv run poe benchmark
# or: python -m benchmarks.run all

# Run Chirp core regression workloads and write a JSON artifact
uv run poe benchmark-core
# or: python -m benchmarks.core --output .benchmarks/core-latest.json

# Run the smallest Pounce 0.7 server smoke benchmark
pounce bench --workers 1 --duration 1 --connections 1

# Run a single framework
python -m benchmarks.run chirp
python -m benchmarks.run fasthtml
python -m benchmarks.run fastapi
python -m benchmarks.run flask
python -m benchmarks.run starlette
python -m benchmarks.run litestar

# Compare GIL vs free-threaded builds explicitly; report headers include GIL mode
uv run --python 3.14 python -m benchmarks.run all
uv run --python 3.14t python -m benchmarks.run all

# Run Chirp experiments (client strategies, Chirp+Uvicorn, sync vs async)
python -m benchmarks.run_experiments

# Run sync vs async comparison (Phase 4a)
python -m benchmarks.run chirp-sync
python -m benchmarks.run chirp-async

# Fused path — Chirp + Pounce with no middleware (fastest JSON/CPU)
python -m benchmarks.run chirp-fused

# Mixed workload — JSON + SSE (Phase 4b, verifies adaptive handoff)
poe benchmark-mixed
# or: CHIRP_WORKER_MODE=sync python -m benchmarks.run_mixed

# Profile Pounce (requires local pounce in PYTHONPATH)
PYTHONPATH=../pounce/src python -m benchmarks.run chirp --profile --client shared-limits
```

## Networked Methodology

| Variable | Value | Notes |
|----------|-------|-------|
| Requests per run | 2000 | Matches Barq PR |
| Concurrent clients | 100 | Matches Barq PR |
| Workers | 10 | Per-framework optimal |
| Rounds | 3 | Reported values are medians across rounds |
| Workloads | JSON, CPU, DB, Template | Same endpoint shape across frameworks |
| Client | Shared pooled httpx.Client | Measures server behavior without per-request client setup churn |

**Workloads:**
- **JSON** — Return `{"message": "hello", "count": 42}`. Minimal framework overhead.
- **CPU** — 50k hash iterations per request. CPU-bound; free-threading benefit most visible.
- **DB** — Query 10 rows from a per-process shared in-memory SQLite database.
- **Template** — Render a 20-item HTML list from Kida (Chirp) or Jinja2 (FastAPI/Flask).

**Servers:**
- Chirp: Pounce (threads on 3.14t, processes on GIL), request queue disabled for benchmarks
- FastHTML: Uvicorn (10 workers; native FastHTML FT element rendering)
- FastAPI: Uvicorn (async)
- Flask: Gunicorn with sync workers
- Starlette: Uvicorn (minimal ASGI)
- Litestar: Uvicorn (modern ASGI)

## Caveats

> **Synthetic benchmarks.** These tests use controlled workloads (JSON, CPU, DB, template) to compare framework performance. They are *not* representative of production traffic. Use "various workloads" or "synthetic benchmarks" in any external claims — avoid "real workloads."

> **Configuration matters.** Results depend on worker count, Python version (GIL vs free-threaded), and load-test parameters. We document our configs; your mileage may vary.

> **Latency includes failed attempts.** Percentiles are calculated across all requests, not only 200 responses, so overload and instability remain visible in the output.

> **Python 3.14t recommended.** Chirp and Pounce are designed for free-threaded Python. Run both `uv run --python 3.14 python -m benchmarks.run all` and `uv run --python 3.14t python -m benchmarks.run all` when making GIL vs free-threaded claims. The report header records Python version, cache tag, and whether the GIL is enabled.

> **Pounce benchmark scope.** `pounce bench` is useful for checking Pounce's
> server behavior with generic ASGI apps. Chirp release claims should continue
> to use this repository's benchmark harness because it exercises Chirp's
> return values, Kida rendering, SSE fanout, and fused sync path.

## Core Regression Workloads

`python -m benchmarks.core` emits a reproducible JSON artifact with:

- Python build metadata, including whether the GIL is enabled.
- OS, CPU, and package versions for Chirp, Pounce, and Kida.
- Per-workload `avg_us`, `p50_us`, and `p99_us` values.

Tracked workloads:

| Workload | What It Measures |
|----------|------------------|
| `template_render` | Full template negotiation and render |
| `fragment_render` | Named block rendering for htmx fragments |
| `oob_serialization` | Primary fragment plus OOB fragment serialization |
| `suspense_first_chunk` | Suspense shell/first-chunk path with deferred blocks |
| `sse_fanout` | Tool event bus fanout plus SSE event encoding |
| `filesystem_route_dispatch` | Discovered filesystem routes compiled into router dispatch |

These are internal regression benchmarks. They are not evidence that Chirp is faster than another framework; they tell us when Chirp got slower at being Chirp.

Example:

```bash
python -m benchmarks.core --iterations 250 --route-count 100 \
  --output .benchmarks/core-latest.json
```

### Release Smoke

For release prep, run the core suite with a stable iteration count and keep the JSON artifact with
the release notes or CI artifacts:

```bash
uv run python -m benchmarks.core --iterations 250 --route-count 100 \
  --output .benchmarks/core-0.6.0.json
```

Compare the workload names, package versions, Python free-threading flags, and broad timing shape
against the previous artifact. Treat large unexplained movement in `template_render`,
`fragment_render`, `oob_serialization`, `suspense_first_chunk`, `sse_fanout`, or
`filesystem_route_dispatch` as a release blocker until it is explained. Do not use this artifact
as a public framework comparison; it is a Chirp hot-path regression check.

### Pull-request regression gate

`.github/workflows/benchmarks.yml` runs three interleaved base/candidate rounds on the same
GitHub-hosted Python 3.14t runner. It compares the median of each workload's per-round `p50_us`,
posts an updatable PR table, and uploads every raw JSON report. Changes above 5% are highlighted;
changes above 20% fail CI. Removing a baseline workload also fails so benchmark coverage cannot
disappear silently. The deliberately broad failure threshold and repeated rounds account for
shared-runner noise; rerun a failure before attributing it to code.

To reproduce the comparison locally:

```bash
python -m benchmarks.compare \
  --baseline base-1.json --baseline base-2.json --baseline base-3.json \
  --candidate candidate-1.json --candidate candidate-2.json --candidate candidate-3.json \
  --markdown-output comparison.md
```

## Output

The values below illustrate the report format; they are not a committed current result artifact
and must not be quoted as comparative performance evidence.

```
============================================================
  CHIRP vs FASTHTML vs FASTAPI vs FLASK vs STARLETTE vs LITESTAR
  Synthetic benchmarks
  Python CPython 3.14.0 (cpython-314t; free-threaded, GIL disabled) | 2000 req, 100 concurrent | 10 workers | median of 3 rounds
============================================================

─── JSON ───
  Chirp        2000/2000 ok, 0 failed, 12000.0 req/s
               latency(all attempts): avg=2.1ms p50=1.9ms p99=7.2ms (→ +141% vs FastAPI)
  Fastapi      2000/2000 ok, 0 failed, 4975.2 req/s
               latency(all attempts): avg=19.3ms p50=18.6ms p99=28.5ms
  Flask        2000/2000 ok, 0 failed, 3500.0 req/s
               ...

─── CPU ───
  ...

─── DB ───
  ...
```

## Structure

```
benchmarks/
├── README.md           # This file
├── run.py              # Orchestrator: start server, load test, report
├── core.py             # In-process Chirp hot-path regression workloads
└── apps/
    ├── chirp_app.py    # Chirp + Pounce
    ├── fasthtml_app.py # FastHTML + Uvicorn
    ├── fastapi_app.py  # FastAPI + Uvicorn
    ├── flask_app.py    # Flask + Gunicorn
    ├── starlette_app.py # Starlette + Uvicorn
    └── litestar_app.py  # Litestar + Uvicorn
```

## Phase 4 (Adaptive Workers)

- **chirp-sync** / **chirp-async** — Compare sync vs async worker mode
- **chirp-fused** — Fused sync path: no middleware, no ASGI; bypasses protocol layer for simple JSON/CPU handlers
- **benchmark-mixed** — JSON + SSE in same app; verifies adaptive handoff

### Target numbers (Python 3.14t, 10 workers)

| Category      | Target   | How                          |
|---------------|----------|------------------------------|
| JSON c=10     | 5000+    | Sync worker, no asyncio       |
| CPU c=10      | 2000+    | Inline sync, no to_thread     |
| JSON c=100    | 2500+    | Sync + accept distributor     |
| CPU c=100     | 1000+    | Sync workers, true parallelism|
| SSE streaming | works    | Async pool handoff            |

Run `python -m benchmarks.run chirp-sync -c 10` to validate JSON/CPU targets.

## Phase 2

- [x] DB workload (SQLite)
- [x] Starlette, Litestar
- [x] GIL vs free-threaded report metadata (3.14 vs 3.14t commands above)

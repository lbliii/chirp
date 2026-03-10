# Chirp Web Framework Benchmarks

Synthetic benchmarks comparing Chirp vs FastAPI vs Flask on JSON and CPU-bound workloads. Designed to demonstrate free-threaded Python performance benefits when using Chirp + Pounce on Python 3.14t.

## Quick Start

```bash
# Install benchmark dependencies
uv sync --extra benchmark
# or: pip install bengal-chirp[benchmark]

# Run all benchmarks
uv run poe benchmark
# or: python -m benchmarks.run all

# Run a single framework
python -m benchmarks.run chirp
python -m benchmarks.run fastapi
python -m benchmarks.run flask

# Run Chirp experiments (client strategies, Chirp+Uvicorn)
python -m benchmarks.run_experiments
```

## Methodology

| Variable | Value | Notes |
|----------|-------|-------|
| Requests per run | 2000 | Matches Barq PR |
| Concurrent clients | 100 | Matches Barq PR |
| Workers | 10 | Per-framework optimal |
| Rounds | 3 | Reported values are medians across rounds |
| Workloads | JSON, CPU | Phase 1; DB + Template in Phase 2 |
| Client | Shared pooled httpx.Client | Measures server behavior without per-request client setup churn |

**Workloads:**
- **JSON** — Return `{"message": "hello", "count": 42}`. Minimal framework overhead.
- **CPU** — 50k hash iterations per request. CPU-bound; free-threading benefit most visible.

**Servers:**
- Chirp: Pounce (threads on 3.14t, processes on GIL), request queue disabled for benchmarks
- FastAPI: Uvicorn (async)
- Flask: Gunicorn with sync workers

## Caveats

> **Synthetic benchmarks.** These tests use controlled workloads (JSON, CPU) to compare framework performance. They are *not* representative of production traffic. Use "various workloads" or "synthetic benchmarks" in any external claims — avoid "real workloads."

> **Configuration matters.** Results depend on worker count, Python version (GIL vs free-threaded), and load-test parameters. We document our configs; your mileage may vary.

> **Latency includes failed attempts.** Percentiles are calculated across all requests, not only 200 responses, so overload and instability remain visible in the output.

> **Python 3.14t recommended.** Chirp and Pounce are designed for free-threaded Python. Run on 3.14t to see the full benefit. On GIL builds, Pounce falls back to multi-process workers.

## Output

```
============================================================
  CHIRP vs FASTAPI vs FLASK (synthetic benchmarks)
  Python 3.14t | 2000 req, 100 concurrent | 10 workers | median of 3 rounds
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
```

## Structure

```
benchmarks/
├── README.md           # This file
├── run.py              # Orchestrator: start server, load test, report
└── apps/
    ├── chirp_app.py    # Chirp + Pounce
    ├── fastapi_app.py  # FastAPI + Uvicorn
    └── flask_app.py    # Flask + Gunicorn
```

## Phase 2 (Planned)

- DB workload (SQLite)
- Template workload (Kida vs Jinja2)
- Starlette, Litestar
- GIL vs free-threaded comparison (3.14 vs 3.14t)

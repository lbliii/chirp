# Chirp Web Framework Benchmark Plan

Draft plan for setting up Chirp benchmarks vs top 3–5 Python web frameworks, modeled on the [Barq example](https://github.com/Quansight-Labs/free-threaded-compatibility/pull/317) in free-threaded-compatibility.

---

## 1. Goals

- Demonstrate free-threaded Python performance benefits for Chirp + Pounce
- Provide credible, reproducible numbers for the [Chirp vs Flask vs FastAPI](https://lbliii.github.io/chirp/docs/about/comparison/) comparison
- Surface Chirp in the free-threaded-compatibility ecosystem
- Avoid misleading claims (see nascheme feedback: avoid "real workloads" for synthetic benchmarks)

---

## 2. Frameworks to Benchmark

| Framework | Concurrency Model | Server | Notes |
|-----------|-------------------|--------|-------|
| **Chirp** | Sync + async, threads on 3.14t | Pounce | Free-threading native |
| **FastAPI** | Async | Uvicorn | Default comparison from Barq PR |
| **Flask** | Sync, WSGI | Gunicorn + sync worker | Common baseline |
| **Starlette** | Async | Uvicorn | Minimal ASGI, isolates framework overhead |
| **Litestar** | Async | Uvicorn | Modern ASGI alternative |

**Optional 5th:** Django (sync, Gunicorn) — adds setup complexity; defer to Phase 2 if needed.

---

## 3. Workloads

Mirror Barq's structure plus Chirp-specific:

| Workload | Description | Chirp Differentiator |
|----------|-------------|----------------------|
| **JSON** | Return `{"message": "hello"}` | Baseline, minimal framework overhead |
| **DB** | SQLite query, return row(s) | I/O scaling; Chirp uses aiosqlite/sqlite3 |
| **CPU** | CPU-bound work (e.g. hash iterations) | Free-threading benefit most visible here |
| **Template** | Render HTML from template | Kida vs Jinja2; Chirp's strength |

Each workload: same logic across frameworks, fair server configs.

---

## 4. Configuration Matrix

| Variable | Values | Notes |
|----------|--------|-------|
| Python | 3.14, 3.14t | Compare GIL vs free-threaded |
| Workers | 4, 8, 10 | Match Barq (10) for comparison |
| Concurrent clients | 100 | Match Barq |
| Requests per run | 2000 | Match Barq |
| Server | Pounce (Chirp), Uvicorn (FastAPI/Starlette/Litestar), Gunicorn (Flask) | Optimal per framework |

---

## 5. Output Metrics

- Requests/second (throughput)
- Latency: avg, p50, p99
- Relative speedup (e.g. "Chirp 141% faster than FastAPI on JSON")
- Clear labeling: "synthetic benchmarks", "various workloads" (not "real workloads")

---

## 6. Repository Structure

```
chirp/
├── benchmarks/
│   ├── README.md           # Methodology, caveats, how to run
│   ├── pyproject.toml      # Benchmark deps (locust, httpx, etc.)
│   ├── apps/
│   │   ├── chirp_app.py
│   │   ├── fastapi_app.py
│   │   ├── flask_app.py
│   │   ├── starlette_app.py
│   │   └── litestar_app.py
│   ├── workloads/
│   │   ├── json.py         # Shared payload, framework-specific handlers
│   │   ├── db.py           # SQLite setup + handlers
│   │   ├── cpu.py          # CPU-bound handler
│   │   └── template.py     # HTML render
│   └── run.py              # Orchestrator: start server, run load test, report
```

**Alternative:** Contribute to `free-threaded-compatibility` as `examples/chirp-benchmarks/` (like Barq). Keeps Chirp-specific logic in chirp repo; compatibility repo gets a minimal runner + link.

---

## 7. Phases

### Phase 1: Minimal (1–2 days)

- [ ] JSON + CPU workloads only
- [ ] Chirp vs FastAPI vs Flask
- [ ] Single Python version (3.14t)
- [ ] `benchmarks/` in chirp repo, runnable via `uv run` or `poe benchmark`

### Phase 2: Full Matrix (2–3 days)

- [ ] Add DB + Template workloads
- [ ] Add Starlette, Litestar
- [ ] Add 3.14 (GIL) vs 3.14t comparison
- [ ] Document methodology in README

### Phase 3: Ecosystem Integration (1 day)

- [ ] PR to free-threaded-compatibility (if desired)
- [ ] Link from Chirp docs comparison page
- [ ] Optional: CI job to run benchmarks on release

---

## 8. Caveats (README Copy)

> **Synthetic benchmarks.** These tests use controlled workloads (JSON, DB, CPU, template) to compare framework performance. They are *not* representative of production traffic. Use "various workloads" or "synthetic benchmarks" in any external claims.
>
> **Configuration matters.** Results depend on worker count, Python version (GIL vs free-threaded), and load-test parameters. We document our configs; your mileage may vary.

---

## 9. Dependencies

- **Load testing:** `locust` or `httpx` + `asyncio` (simple script)
- **SQLite:** `aiosqlite` (async frameworks), `sqlite3` (sync)
- **Templates:** Kida (Chirp), Jinja2 (others for fair comparison)

---

## 10. Success Criteria

- [ ] Benchmarks run reproducibly on 3.14t
- [ ] README explains methodology and caveats
- [ ] Numbers support "Chirp benefits from free-threading" narrative without overclaiming
- [ ] Results can be cited in Chirp vs Flask vs FastAPI content (content brief #4)

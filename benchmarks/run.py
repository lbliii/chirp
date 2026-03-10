"""Benchmark runner — start server, run load test, report.

Usage:
    uv run python benchmarks/run.py [chirp|fastapi|flask|all]
    uv run python benchmarks/run.py all  # default

Requires: chirp, fastapi, uvicorn, flask, gunicorn, httpx
Install: uv sync --group benchmark  (or pip install chirp[benchmark])
"""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx

# Config (match Barq PR)
NUM_REQUESTS = 2000
CONCURRENCY = 100
WORKERS = 10
BASE_PORT = 9000


@dataclass
class BenchResult:
    """Result for one framework + workload."""

    framework: str
    workload: str
    ok: int
    total: int
    req_per_sec: float
    avg_ms: float
    p50_ms: float
    p99_ms: float


def wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """Poll until server responds or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def run_load_test(url: str, num_requests: int, concurrency: int) -> BenchResult | None:
    """Run load test and return stats. Returns None if framework name unknown."""
    latencies: list[float] = []
    ok = 0

    def worker() -> tuple[bool, float]:
        with httpx.Client(timeout=30.0) as client:
            start = time.perf_counter()
            try:
                r = client.get(url)
                elapsed = (time.perf_counter() - start) * 1000
                return r.status_code == 200, elapsed
            except Exception:
                elapsed = (time.perf_counter() - start) * 1000
                return False, elapsed

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(worker) for _ in range(num_requests)]
        for f in as_completed(futures):
            success, lat = f.result()
            if success:
                ok += 1
                latencies.append(lat)
    elapsed = time.perf_counter() - start

    if not latencies:
        return None

    latencies.sort()
    n = len(latencies)
    req_per_sec = ok / elapsed if elapsed else 0.0
    return BenchResult(
        framework="",  # filled by caller
        workload="",
        ok=ok,
        total=num_requests,
        req_per_sec=req_per_sec,
        avg_ms=sum(latencies) / n,
        p50_ms=latencies[n // 2],
        p99_ms=latencies[int(n * 0.99)] if n > 1 else latencies[0],
    )


def run_chirp(port: int) -> subprocess.Popen[bytes]:
    """Start Chirp server."""
    env = os.environ.copy()
    env["BENCH_PORT"] = str(port)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os; from benchmarks.apps.chirp_app import app; "
                "app.run(host='127.0.0.1', port=int(os.environ.get('BENCH_PORT', 8000)))"
            ),
        ],
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def run_fastapi(port: int) -> subprocess.Popen[bytes]:
    """Start FastAPI server via uvicorn."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "benchmarks.apps.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            str(WORKERS),
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def run_flask(port: int) -> subprocess.Popen[bytes]:
    """Start Flask server via gunicorn."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "-w",
            str(WORKERS),
            "-b",
            f"127.0.0.1:{port}",
            "benchmarks.apps.flask_app:app",
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def run_framework(name: str, port: int) -> list[BenchResult]:
    """Start server, run JSON and CPU benchmarks, stop server."""
    if name == "chirp":
        proc = run_chirp(port)
    elif name == "fastapi":
        proc = run_fastapi(port)
    elif name == "flask":
        proc = run_flask(port)
    else:
        return []

    base = f"http://127.0.0.1:{port}"
    results: list[BenchResult] = []

    try:
        if not wait_for_server(f"{base}/json"):
            print(f"  {name}: server failed to start", file=sys.stderr)
            return []

        for workload, path in [("json", "/json"), ("cpu", "/cpu")]:
            r = run_load_test(f"{base}{path}", NUM_REQUESTS, CONCURRENCY)
            if r:
                r.framework = name
                r.workload = workload
                results.append(r)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    return results


def print_report(results: list[BenchResult]) -> None:
    """Print formatted benchmark report."""
    frameworks = sorted({r.framework for r in results})
    workloads = sorted({r.workload for r in results})

    print()
    print("=" * 60)
    print("  CHIRP vs FASTAPI vs FLASK (synthetic benchmarks)")
    print(f"  {NUM_REQUESTS} requests, {CONCURRENCY} concurrent clients")
    print(f"  Workers: {WORKERS}")
    print("=" * 60)
    print()

    for workload in workloads:
        print(f"─── {workload.upper()} ───")
        by_fw = {r.framework: r for r in results if r.workload == workload}
        baseline = by_fw.get("fastapi") or next(iter(by_fw.values()))
        for fw in frameworks:
            r = by_fw.get(fw)
            if not r:
                continue
            pct = (
                (r.req_per_sec / baseline.req_per_sec - 1) * 100
                if baseline.req_per_sec and fw != baseline.framework
                else 0
            )
            pct_str = (
                f" (→ {pct:+.0f}% vs FastAPI)"
                if fw != "fastapi" and baseline.framework == "fastapi"
                else ""
            )
            print(f"  {fw.capitalize():12} {r.ok}/{r.total} ok, {r.req_per_sec:.1f} req/s")
            print(
                f"               latency: avg={r.avg_ms:.1f}ms p50={r.p50_ms:.1f}ms p99={r.p99_ms:.1f}ms{pct_str}"
            )
        print()
    print("Synthetic benchmarks — not representative of production workloads.")


def main() -> None:
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    if "all" in targets:
        targets = ["chirp", "fastapi", "flask"]

    all_results: list[BenchResult] = []
    ports = {name: BASE_PORT + i for i, name in enumerate(["chirp", "fastapi", "flask"])}

    for name in targets:
        if name not in ports:
            print(f"Unknown framework: {name}", file=sys.stderr)
            continue
        print(f"Running {name}...", flush=True)
        results = run_framework(name, ports[name])
        all_results.extend(results)

    if all_results:
        print_report(all_results)


if __name__ == "__main__":
    main()

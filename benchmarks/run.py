"""Benchmark runner — start server, run load test, report.

Usage:
    uv run python -m benchmarks.run [chirp|fastapi|flask|chirp-uvicorn|all]
    uv run python -m benchmarks.run all  # default

    # Experiments (from benchmark-pounce-chirp-deep-dive.md):
    uv run python -m benchmarks.run chirp --concurrency 10   # match workers
    uv run python -m benchmarks.run chirp --client per-request  # baseline
    uv run python -m benchmarks.run chirp-uvicorn  # Chirp behind Uvicorn

    # Run on Python 3.14t (free-threaded) to see Chirp benefit:
    uv run --python 3.14t python -m benchmarks.run all

Requires: chirp, fastapi, uvicorn, flask, gunicorn, httpx
Install: uv sync --extra benchmark  (or pip install chirp[benchmark])
"""

import argparse
import contextlib
import os
import statistics
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
ROUNDS = 3
BASE_PORT = 9000


@dataclass
class BenchResult:
    """Result for one framework + workload."""

    framework: str
    workload: str
    ok: int
    failed: int
    total: int
    req_per_sec: float
    avg_ms: float
    p50_ms: float
    p99_ms: float
    rounds: int = 1


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """Poll until server responds consistently or timeout."""
    deadline = time.monotonic() + timeout
    consecutive_ok = 0
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(url)
                if r.status_code == 200:
                    consecutive_ok += 1
                    if consecutive_ok >= 3:
                        return True
                else:
                    consecutive_ok = 0
            except Exception:
                consecutive_ok = 0
            time.sleep(0.1)
    return False


def run_load_test(
    url: str,
    num_requests: int,
    concurrency: int,
    *,
    client_strategy: str = "shared-limits",
) -> BenchResult:
    """Run load test and return stats.

    client_strategy:
      - "shared-limits": Single shared httpx.Client with max_connections=concurrency
      - "per-request": Per-request client (baseline, avoids shared-client contention)
    Latency stats include failed attempts, not just successful responses.
    """
    latencies: list[float] = []
    ok = 0

    if client_strategy == "per-request":

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
                latencies.append(lat)
                if success:
                    ok += 1
        elapsed = time.perf_counter() - start
    else:
        # shared-limits
        limits = httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=concurrency,
        )

        def worker(client: httpx.Client) -> tuple[bool, float]:
            start = time.perf_counter()
            try:
                r = client.get(url)
                elapsed = (time.perf_counter() - start) * 1000
                return r.status_code == 200, elapsed
            except Exception:
                elapsed = (time.perf_counter() - start) * 1000
                return False, elapsed

        start = time.perf_counter()
        with (
            httpx.Client(timeout=30.0, limits=limits) as client,
            ThreadPoolExecutor(max_workers=concurrency) as ex,
        ):
            futures = [ex.submit(worker, client) for _ in range(num_requests)]
            for f in as_completed(futures):
                success, lat = f.result()
                latencies.append(lat)
                if success:
                    ok += 1
        elapsed = time.perf_counter() - start

    latencies.sort()
    n = len(latencies)
    req_per_sec = ok / elapsed if elapsed else 0.0
    return BenchResult(
        framework="",  # filled by caller
        workload="",
        ok=ok,
        failed=num_requests - ok,
        total=num_requests,
        req_per_sec=req_per_sec,
        avg_ms=sum(latencies) / n,
        p50_ms=latencies[n // 2],
        p99_ms=latencies[int(n * 0.99)] if n > 1 else latencies[0],
    )


def warmup_endpoint(url: str, attempts: int = 10) -> None:
    """Warm an endpoint with keep-alive requests before timing."""
    with httpx.Client(timeout=5.0) as client:
        for _ in range(attempts):
            with contextlib.suppress(Exception):
                client.get(url)
            time.sleep(0.05)


def aggregate_rounds(rounds: list[BenchResult]) -> BenchResult:
    """Aggregate repeated benchmark rounds using medians."""
    first = rounds[0]
    return BenchResult(
        framework=first.framework,
        workload=first.workload,
        ok=round(statistics.median(r.ok for r in rounds)),
        failed=round(statistics.median(r.failed for r in rounds)),
        total=first.total,
        req_per_sec=statistics.median(r.req_per_sec for r in rounds),
        avg_ms=statistics.median(r.avg_ms for r in rounds),
        p50_ms=statistics.median(r.p50_ms for r in rounds),
        p99_ms=statistics.median(r.p99_ms for r in rounds),
        rounds=len(rounds),
    )


def run_chirp(
    port: int,
    *,
    profile: bool = False,
    worker_mode: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start Chirp server. worker_mode: sync | async | None (auto)."""
    env = os.environ.copy()
    env["BENCH_PORT"] = str(port)
    if worker_mode is not None:
        env["CHIRP_WORKER_MODE"] = worker_mode
    if profile:
        env["POUNCE_PROFILE"] = "1"
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
        stderr=None if profile else subprocess.DEVNULL,
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


def run_chirp_uvicorn(port: int) -> subprocess.Popen[bytes]:
    """Start Chirp app via Uvicorn (experiment: Chirp without Pounce)."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "benchmarks.apps.chirp_app:app",
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


def run_framework(
    name: str,
    port: int,
    *,
    concurrency: int = CONCURRENCY,
    client_strategy: str = "shared-limits",
    profile: bool = False,
) -> list[BenchResult]:
    """Start server, run benchmark rounds, stop server."""
    if name == "chirp":
        proc = run_chirp(port, profile=profile)
    elif name == "chirp-sync":
        proc = run_chirp(port, worker_mode="sync")  # Force sync workers
    elif name == "chirp-fused":
        proc = run_chirp(port, worker_mode="sync")  # Fused path auto-activates in sync mode
    elif name == "chirp-async":
        proc = run_chirp(port, worker_mode="async")  # Force async workers
    elif name == "chirp-uvicorn":
        proc = run_chirp_uvicorn(port)
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
            url = f"{base}{path}"
            warmup_endpoint(url)
            workload_rounds: list[BenchResult] = []
            for _round in range(ROUNDS):
                r = run_load_test(
                    url,
                    NUM_REQUESTS,
                    concurrency,
                    client_strategy=client_strategy,
                )
                r.framework = name
                r.workload = workload
                workload_rounds.append(r)
            results.append(aggregate_rounds(workload_rounds))
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    return results


def print_report(
    results: list[BenchResult],
    *,
    concurrency: int = CONCURRENCY,
    client_strategy: str = "shared-limits",
) -> None:
    """Print formatted benchmark report."""
    frameworks = sorted({r.framework for r in results})
    workloads = sorted({r.workload for r in results})
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    try:
        free_threaded = not sys._is_gil_enabled()
    except AttributeError:
        free_threaded = False
    py_label = f"{py_ver}t" if free_threaded else py_ver

    print()
    print("=" * 60)
    print("  CHIRP vs FASTAPI vs FLASK (synthetic benchmarks)")
    print(
        f"  Python {py_label} | {NUM_REQUESTS} req, {concurrency} concurrent | "
        f"{WORKERS} workers | client={client_strategy} | median of {ROUNDS} rounds"
    )
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
            print(
                f"  {fw.capitalize():12} {r.ok}/{r.total} ok, "
                f"{r.failed} failed, {r.req_per_sec:.1f} req/s"
            )
            print(
                f"               latency(all attempts): avg={r.avg_ms:.1f}ms "
                f"p50={r.p50_ms:.1f}ms p99={r.p99_ms:.1f}ms{pct_str}"
            )
        print()
    print("Synthetic benchmarks — not representative of production workloads.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark Chirp vs FastAPI vs Flask",
        epilog="Experiments: chirp --concurrency 10 | chirp --client per-request | chirp-uvicorn",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["all"],
        help="chirp, chirp-sync, chirp-fused, chirp-async, fastapi, flask, chirp-uvicorn, or all",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=CONCURRENCY,
        help=f"Concurrent client threads (default: {CONCURRENCY})",
    )
    parser.add_argument(
        "--client",
        choices=["shared-limits", "per-request"],
        default="shared-limits",
        help="Client strategy: shared-limits (default) or per-request",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable POUNCE_PROFILE for Chirp (logs read/parse/app/drain timings to stderr)",
    )
    args = parser.parse_args()

    targets = args.targets if args.targets != ["all"] else ["chirp", "fastapi", "flask"]
    if "all" in targets:
        targets = ["chirp", "fastapi", "flask"]

    all_frameworks = [
        "chirp",
        "chirp-sync",
        "chirp-fused",
        "chirp-async",
        "chirp-uvicorn",
        "fastapi",
        "flask",
    ]
    ports = {name: BASE_PORT + i for i, name in enumerate(all_frameworks)}

    all_results: list[BenchResult] = []
    for name in targets:
        if name not in ports:
            print(f"Unknown framework: {name}", file=sys.stderr)
            continue
        print(
            f"Running {name} (concurrency={args.concurrency}, client={args.client})...", flush=True
        )
        results = run_framework(
            name,
            ports[name],
            concurrency=args.concurrency,
            client_strategy=args.client,
            profile=args.profile and name == "chirp",
        )
        all_results.extend(results)

    if all_results:
        print_report(
            all_results,
            concurrency=args.concurrency,
            client_strategy=args.client,
        )


if __name__ == "__main__":
    main()

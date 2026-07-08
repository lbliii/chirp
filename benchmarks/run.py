"""Benchmark runner — start server, run load test, report.

Usage:
    uv run python -m benchmarks.run [chirp|fasthtml|fastapi|flask|starlette|litestar|all]
    uv run python -m benchmarks.run all  # default

    # Experiments (from benchmark-pounce-chirp-deep-dive.md):
    uv run python -m benchmarks.run chirp --concurrency 10   # match workers
    uv run python -m benchmarks.run chirp --client per-request  # baseline
    uv run python -m benchmarks.run chirp-uvicorn  # Chirp behind Uvicorn

    # Run on Python 3.14t (free-threaded) to see Chirp benefit:
    uv run --python 3.14t python -m benchmarks.run all

Requires: chirp, FastHTML, FastAPI, uvicorn, Flask, Gunicorn, Starlette, Litestar, httpx
Install: uv sync --extra benchmark  (or pip install chirp[benchmark])
"""

import argparse
import contextlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx

# Config (match Barq PR)
NUM_REQUESTS = 2000
CONCURRENCY = 100
WORKERS = 10
ROUNDS = 3
BASE_PORT = 9000
NETWORKED_WORKLOADS = (
    ("json", "/json"),
    ("cpu", "/cpu"),
    ("db", "/db"),
    ("template", "/template"),
)
DEFAULT_TARGETS = ["chirp", "fasthtml", "fastapi", "flask", "starlette", "litestar"]
EXPERIMENT_TARGETS = ["chirp-sync", "chirp-fused", "chirp-async", "chirp-uvicorn"]
ALL_FRAMEWORKS = [*DEFAULT_TARGETS, *EXPERIMENT_TARGETS]
REPORT_SCHEMA_VERSION = 1
README_BASELINE_START = "<!-- networked-baseline:start -->"
README_BASELINE_END = "<!-- networked-baseline:end -->"
BENCHMARK_PACKAGES = (
    "bengal-chirp",
    "bengal-pounce",
    "kida-templates",
    "python-fasthtml",
    "fastapi",
    "flask",
    "starlette",
    "litestar",
    "uvicorn",
    "gunicorn",
    "httpx",
)


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


def python_runtime_metadata() -> dict[str, str | bool]:
    """Return Python runtime metadata for comparison reports."""
    try:
        gil_enabled = sys._is_gil_enabled()
    except AttributeError:
        gil_enabled = True
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "cache_tag": sys.implementation.cache_tag,
        "gil_enabled": gil_enabled,
        "free_threaded": not gil_enabled,
    }


def python_runtime_label() -> str:
    """Return a compact Python label that makes GIL mode explicit."""
    metadata = python_runtime_metadata()
    gil_mode = "free-threaded, GIL disabled" if metadata["free_threaded"] else "GIL enabled"
    return (
        f"{metadata['implementation']} {metadata['version']} ({metadata['cache_tag']}; {gil_mode})"
    )


def _package_versions() -> dict[str, str]:
    packages: dict[str, str] = {}
    for package in BENCHMARK_PACKAGES:
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = "not-installed"
    return packages


def _source_revision() -> dict[str, str | bool]:
    root = Path(__file__).resolve().parents[1]
    git = shutil.which("git")
    if git is None:
        return {"commit": "unknown", "dirty": True}
    try:
        commit = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                [git, "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except OSError, subprocess.CalledProcessError:
        return {"commit": "unknown", "dirty": True}
    return {"commit": commit, "dirty": dirty}


def build_network_report(
    results: list[BenchResult],
    *,
    targets: list[str],
    concurrency: int,
    client_strategy: str,
) -> dict[str, object]:
    """Build a versioned, self-describing cross-framework benchmark artifact."""
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "suite": "chirp-networked-framework-comparison",
        "captured_at": datetime.now(UTC).isoformat(),
        "source": _source_revision(),
        "environment": {
            "python": python_runtime_metadata(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "packages": _package_versions(),
        },
        "config": {
            "requests_per_round": NUM_REQUESTS,
            "concurrency": concurrency,
            "workers": WORKERS,
            "rounds": ROUNDS,
            "client_strategy": client_strategy,
            "targets": targets,
            "workloads": [name for name, _path in NETWORKED_WORKLOADS],
        },
        "results": [asdict(result) for result in results],
    }


def write_network_report(report: dict[str, object], output: Path) -> None:
    """Write a network benchmark artifact with deterministic formatting."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_baseline_table(report: dict[str, object], *, artifact_link: str) -> str:
    """Render the committed README table from a versioned benchmark artifact."""
    config = report["config"]
    environment = report["environment"]
    assert isinstance(config, dict)
    assert isinstance(environment, dict)
    targets = config["targets"]
    workloads = config["workloads"]
    results = report["results"]
    python = environment["python"]
    assert isinstance(targets, list)
    assert isinstance(workloads, list)
    assert isinstance(results, list)
    assert isinstance(python, dict)
    by_key = {(item["framework"], item["workload"]): item for item in results}

    gil_mode = "GIL disabled" if python["free_threaded"] else "GIL enabled"
    captured_at = str(report["captured_at"])
    target_args = "all" if targets == DEFAULT_TARGETS else " ".join(targets)
    output_arg = (Path("benchmarks") / artifact_link).as_posix()
    command = (
        f"uv run python -m benchmarks.run {target_args} "
        f"--concurrency {config['concurrency']} --client {config['client_strategy']} "
        f"--output {output_arg} --readme-table benchmarks/README.md"
    )
    lines = [
        "### Committed network baseline",
        "",
        (
            f"Captured {captured_at[:10]} on {environment['machine']} with "
            f"{python['implementation']} {python['version']} ({gil_mode}); "
            f"{config['requests_per_round']} requests x {config['rounds']} rounds, "
            f"{config['concurrency']} concurrent clients, {config['workers']} workers. "
            f"[Full artifact]({artifact_link})."
        ),
        "",
        f"Regenerate from the repository root: `{command}`",
        "",
        "| Framework | JSON req/s (p50) | CPU req/s (p50) | DB req/s (p50) | HTML req/s (p50) | Failed attempts |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for target in targets:
        cells: list[str] = []
        failed = 0
        for workload in workloads:
            item = by_key.get((target, workload))
            if item is None:
                cells.append("not measured")
                continue
            cells.append(f"{item['req_per_sec']:.1f} ({item['p50_ms']:.1f} ms)")
            failed += int(item["failed"])
        lines.append(f"| {target} | {' | '.join(cells)} | {failed} |")
    lines.extend(
        [
            "",
            "Values are medians across rounds. Latency and failure accounting include every attempt. "
            "This is a synthetic comparison, not a production-capacity claim.",
        ]
    )
    return "\n".join(lines)


def update_readme_baseline(readme: Path, table: str) -> None:
    """Replace the generated baseline section between stable README markers."""
    content = readme.read_text(encoding="utf-8")
    if README_BASELINE_START not in content or README_BASELINE_END not in content:
        msg = f"{readme} is missing networked baseline markers"
        raise ValueError(msg)
    before, remainder = content.split(README_BASELINE_START, 1)
    _old, after = remainder.split(README_BASELINE_END, 1)
    replacement = f"{README_BASELINE_START}\n{table}\n{README_BASELINE_END}"
    readme.write_text(f"{before}{replacement}{after}", encoding="utf-8")


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


def run_fasthtml(port: int) -> subprocess.Popen[bytes]:
    """Start FastHTML via the same Uvicorn worker topology as the ASGI peers."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "benchmarks.apps.fasthtml_app:app",
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


def run_starlette(port: int) -> subprocess.Popen[bytes]:
    """Start Starlette server via uvicorn."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "benchmarks.apps.starlette_app:app",
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


def run_litestar(port: int) -> subprocess.Popen[bytes]:
    """Start Litestar server via uvicorn."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "benchmarks.apps.litestar_app:app",
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
    elif name == "fasthtml":
        proc = run_fasthtml(port)
    elif name == "flask":
        proc = run_flask(port)
    elif name == "starlette":
        proc = run_starlette(port)
    elif name == "litestar":
        proc = run_litestar(port)
    else:
        return []

    base = f"http://127.0.0.1:{port}"
    results: list[BenchResult] = []

    try:
        if not wait_for_server(f"{base}/json"):
            print(f"  {name}: server failed to start", file=sys.stderr)
            return []

        for workload, path in NETWORKED_WORKLOADS:
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

    print()
    print("=" * 60)
    print("  CHIRP vs FASTHTML vs FASTAPI vs FLASK vs STARLETTE vs LITESTAR")
    print("  Synthetic benchmarks")
    print(
        f"  Python {python_runtime_label()} | {NUM_REQUESTS} req, {concurrency} concurrent | "
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
        description="Benchmark Chirp vs FastHTML vs FastAPI vs Flask vs Starlette vs Litestar",
        epilog="Experiments: chirp --concurrency 10 | chirp --client per-request | chirp-uvicorn",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["all"],
        help=(
            "chirp, fasthtml, fastapi, flask, starlette, litestar, chirp-sync, chirp-fused, "
            "chirp-async, chirp-uvicorn, or all"
        ),
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
    parser.add_argument(
        "--output",
        type=Path,
        help="Write a versioned JSON result artifact",
    )
    parser.add_argument(
        "--readme-table",
        type=Path,
        help="Regenerate the marked baseline table (requires --output)",
    )
    args = parser.parse_args()
    if args.readme_table is not None and args.output is None:
        parser.error("--readme-table requires --output")

    targets = args.targets if args.targets != ["all"] else DEFAULT_TARGETS
    if "all" in targets:
        targets = DEFAULT_TARGETS

    ports = {name: BASE_PORT + i for i, name in enumerate(ALL_FRAMEWORKS)}

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
        if args.output is not None:
            report = build_network_report(
                all_results,
                targets=targets,
                concurrency=args.concurrency,
                client_strategy=args.client,
            )
            write_network_report(report, args.output)
            if args.readme_table is not None:
                artifact_link = os.path.relpath(args.output, args.readme_table.parent)
                update_readme_baseline(
                    args.readme_table,
                    render_baseline_table(report, artifact_link=Path(artifact_link).as_posix()),
                )


if __name__ == "__main__":
    main()

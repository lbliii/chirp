#!/usr/bin/env python3
"""Mixed workload benchmark — JSON + SSE in same app.

Verifies adaptive dispatch: /json uses sync path (fast), /stream hands off
to async pool. Run with Chirp sync workers (worker_mode=sync) to validate
handoff works.

Usage:
    uv run python -m benchmarks.run_mixed
    CHIRP_WORKER_MODE=sync uv run python -m benchmarks.run_mixed
"""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

NUM_JSON_REQUESTS = 1000
NUM_STREAM_REQUESTS = 50
CONCURRENCY = 20
BASE_PORT = 9010
ROUNDS = 2


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
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


def run_json_load(url: str, num: int, concurrency: int) -> tuple[int, int, float]:
    """Run JSON load test. Returns (ok, failed, req_per_sec)."""
    ok = 0
    start = time.perf_counter()
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    def worker(client: httpx.Client) -> bool:
        try:
            r = client.get(url)
            return r.status_code == 200
        except Exception:
            return False

    with httpx.Client(timeout=30.0, limits=limits) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(worker, client) for _ in range(num)]
            for f in as_completed(futures):
                if f.result():
                    ok += 1
    elapsed = time.perf_counter() - start
    return ok, num - ok, ok / elapsed if elapsed else 0.0


def run_stream_smoke(url: str, num: int, concurrency: int) -> tuple[int, int]:
    """Connect to SSE stream, read a few events, close. Returns (ok, failed)."""
    ok = 0

    def one_request() -> bool:
        try:
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", url) as r:
                    if r.status_code != 200:
                        return False
                    count = 0
                    for _ in r.iter_lines():
                        count += 1
                        if count >= 10:  # Read a few events then stop
                            break
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(one_request) for _ in range(num)]
        for f in as_completed(futures):
            if f.result():
                ok += 1
    return ok, num - ok


def main() -> None:
    worker_mode = os.environ.get("CHIRP_WORKER_MODE", "auto")
    port = BASE_PORT
    env = os.environ.copy()
    env["BENCH_PORT"] = str(port)
    env["CHIRP_WORKER_MODE"] = worker_mode

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os; from benchmarks.apps.chirp_app_mixed import app; "
                "app.run(host='127.0.0.1', port=int(os.environ.get('BENCH_PORT', 8000)))"
            ),
        ],
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        if not wait_for_server(f"{base}/json"):
            print("Server failed to start", file=sys.stderr)
            sys.exit(1)

        print("=" * 60)
        print(f"  Mixed workload (JSON + SSE) | worker_mode={worker_mode}")
        print(f"  {NUM_JSON_REQUESTS} JSON + {NUM_STREAM_REQUESTS} stream | {CONCURRENCY} concurrent")
        print("=" * 60)

        json_ok, json_failed, json_rps = 0, 0, 0.0
        stream_ok, stream_failed = 0, 0
        for rnd in range(ROUNDS):
            # Run JSON and stream concurrently
            with ThreadPoolExecutor(max_workers=2) as ex:
                j_f = ex.submit(run_json_load, f"{base}/json", NUM_JSON_REQUESTS, CONCURRENCY)
                s_f = ex.submit(run_stream_smoke, f"{base}/stream", NUM_STREAM_REQUESTS, CONCURRENCY)
                jo, jf, jr = j_f.result()
                so, sf = s_f.result()
            json_ok += jo
            json_failed += jf
            json_rps += jr
            stream_ok += so
            stream_failed += sf

        json_ok //= ROUNDS
        json_failed //= ROUNDS
        json_rps /= ROUNDS
        stream_ok //= ROUNDS
        stream_failed //= ROUNDS

        print()
        print(f"  JSON:  {json_ok}/{NUM_JSON_REQUESTS} ok, {json_failed} failed, {json_rps:.1f} req/s")
        print(f"  Stream: {stream_ok}/{NUM_STREAM_REQUESTS} ok, {stream_failed} failed")
        print()
        if stream_failed > 0:
            print("  Stream handoff may have failed. Check worker_mode=async if using sync.")
        else:
            print("  Adaptive dispatch OK: both JSON and SSE work.")
        print()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()

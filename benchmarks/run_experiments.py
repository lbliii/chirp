#!/usr/bin/env python3
"""Run benchmark experiments from docs/benchmark-pounce-chirp-deep-dive.md.

Executes the recommended experiments to isolate the shared-client bottleneck:
1. Chirp with per-request client (baseline)
2. Chirp with shared client + limits, concurrency=100
3. Chirp with shared client + limits, concurrency=10 (match workers)
4. Chirp behind Uvicorn (Chirp without Pounce)

Usage:
    uv run python -m benchmarks.run_experiments
"""

import subprocess
import sys


def run(cmd: list[str], label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "chirp", *cmd],
        cwd=".",
    )


def main() -> None:
    print("Benchmark experiments (docs/benchmark-pounce-chirp-deep-dive.md)")
    print("Running Chirp variants — compare client strategies and servers")

    run(
        ["--client", "per-request"],
        "1. Baseline: per-request client (no shared-client contention)",
    )
    run(
        ["--client", "shared-limits"],
        "2. Shared client + limits, concurrency=100",
    )
    run(
        ["--client", "shared-limits", "--concurrency", "10"],
        "3. Shared client + limits, concurrency=10 (match workers)",
    )
    print("\n" + "=" * 60)
    print("  4. Chirp behind Uvicorn (Chirp without Pounce)")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "chirp-uvicorn"],
        cwd=".",
    )
    print("\n" + "=" * 60)
    print("  5. Chirp+Pounce sync mode (worker_mode=sync)")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "chirp-sync"],
        cwd=".",
    )
    print("\n" + "=" * 60)
    print("  6. Chirp+Pounce async mode (worker_mode=async)")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "chirp-async"],
        cwd=".",
    )

    print("\n" + "=" * 60)
    print("  Experiments complete. Compare req/s across runs.")
    print("=" * 60)


if __name__ == "__main__":
    main()

"""Live PostgreSQL benchmarks for Pelt's concurrency and bulk boundaries.

Run with a disposable PostgreSQL database::

    CHIRP_BENCH_PG_DSN=postgresql://chirp:chirp@localhost/chirp_bench \
      uv run python -m benchmarks.pelt

The aggregate workload measures independent prepared-query round trips on
separate checked-out connections. The stream and executemany workloads are
reported separately because one cursor and one sequential bulk loop are not
expected to scale with pool size.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from itertools import pairwise
from pathlib import Path
from typing import Any

from chirp.data import Database
from chirp.data.drivers._pelt import pool as pelt_pool
from chirp.data.drivers._pelt.types import PoolConfig

REPORT_SCHEMA_VERSION = 1
DEFAULT_CONCURRENCY = (1, 2, 4, 8)
DEFAULT_QUERIES = 1000
DEFAULT_WARMUP = 10
DEFAULT_STREAM_ROWS = 10_000
DEFAULT_STREAM_BATCH_SIZE = 100
DEFAULT_BULK_ROWS = 500


@dataclass(frozen=True, slots=True)
class _ValueRow:
    value: int


def _package_version(name: str) -> str | None:
    with contextlib.suppress(metadata.PackageNotFoundError):
        return metadata.version(name)
    return None


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


def _python_metadata() -> dict[str, str | bool]:
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


def parse_concurrency(value: str) -> tuple[int, ...]:
    """Parse a strictly increasing comma-separated concurrency series."""
    try:
        levels = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        msg = "concurrency must be comma-separated positive integers"
        raise argparse.ArgumentTypeError(msg) from exc
    if not levels or any(level < 1 for level in levels):
        msg = "concurrency must contain positive integers"
        raise argparse.ArgumentTypeError(msg)
    if levels[0] != 1:
        msg = "concurrency must start at 1 so speedup has a baseline"
        raise argparse.ArgumentTypeError(msg)
    if any(current <= previous for previous, current in pairwise(levels)):
        msg = "concurrency values must be unique and strictly increasing"
        raise argparse.ArgumentTypeError(msg)
    return levels


def allocate_queries(total: int, workers: int) -> tuple[int, ...]:
    """Distribute ``total`` queries across workers without dropping remainder."""
    if total < workers or workers < 1:
        msg = f"total queries ({total}) must be >= workers ({workers}) >= 1"
        raise ValueError(msg)
    quotient, remainder = divmod(total, workers)
    return tuple(quotient + (index < remainder) for index in range(workers))


def _percentiles_us(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "avg_us": round(statistics.mean(ordered), 3),
        "p50_us": round(ordered[len(ordered) // 2], 3),
        "p99_us": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))], 3),
    }


async def _server_version(dsn: str) -> str:
    conn = await pelt_pool.connect(dsn)
    try:
        row = await conn.fetchrow("SHOW server_version")
    finally:
        await conn.close()
    if row is None:
        msg = "PostgreSQL returned no server_version row"
        raise RuntimeError(msg)
    return str(row["server_version"])


async def measure_aggregate_queries(
    dsn: str,
    *,
    total_queries: int,
    concurrency: int,
    warmup: int,
) -> dict[str, Any]:
    """Measure independent query round trips on dedicated checked-out connections."""
    counts = allocate_queries(total_queries, concurrency)
    pool = await pelt_pool.create_pool(
        PoolConfig.from_dsn(dsn, min_size=concurrency, max_size=concurrency)
    )
    connections = [await pool.acquire() for _ in range(concurrency)]
    latencies_us: list[float] = []
    sql = "SELECT $1::int8 AS value"

    async def run_worker(index: int, query_count: int) -> None:
        conn = connections[index]
        for query_index in range(query_count):
            value = index * total_queries + query_index
            started = time.perf_counter()
            row = await conn.fetchrow(sql, value)
            latencies_us.append((time.perf_counter() - started) * 1_000_000)
            assert row is not None
            assert row["value"] == value

    try:
        for conn in connections:
            for warmup_index in range(warmup):
                row = await conn.fetchrow(sql, -(warmup_index + 1))
                assert row is not None

        started = time.perf_counter()
        await asyncio.gather(*(run_worker(index, count) for index, count in enumerate(counts)))
        elapsed = time.perf_counter() - started
    finally:
        try:
            for conn in connections:
                await pool.release(conn)
        finally:
            await pool.close()

    return {
        "name": "aggregate_prepared_queries",
        "concurrency": concurrency,
        "queries": total_queries,
        "elapsed_s": round(elapsed, 6),
        "queries_per_second": round(total_queries / elapsed, 3),
        **_percentiles_us(latencies_us),
    }


async def measure_single_stream(
    dsn: str,
    *,
    rows: int,
    batch_size: int,
) -> dict[str, Any]:
    """Measure one ordered server cursor through the public Database facade."""
    database = Database(dsn, pool_size=1)
    await database.connect()
    seen = 0
    checksum = 0
    started = time.perf_counter()
    try:
        async for row in database.stream(
            _ValueRow,
            "SELECT generate_series(1, $1)::int4 AS value",
            rows,
            batch_size=batch_size,
        ):
            seen += 1
            checksum += row.value
        elapsed = time.perf_counter() - started
    finally:
        await database.disconnect()
    expected_checksum = rows * (rows + 1) // 2
    if seen != rows or checksum != expected_checksum:
        msg = (
            f"stream integrity failure: rows={seen}/{rows}, checksum={checksum}/{expected_checksum}"
        )
        raise RuntimeError(msg)
    return {
        "name": "single_server_cursor",
        "rows": rows,
        "batch_size": batch_size,
        "elapsed_s": round(elapsed, 6),
        "rows_per_second": round(rows / elapsed, 3),
        "checksum": checksum,
    }


async def measure_executemany_loop(dsn: str, *, rows: int) -> dict[str, Any]:
    """Measure Pelt's current sequential executemany convenience loop."""
    conn = await pelt_pool.connect(dsn)
    try:
        await conn.execute("CREATE TEMP TABLE pelt_benchmark_bulk (value int8 NOT NULL)")
        values = [(value,) for value in range(rows)]
        started = time.perf_counter()
        await conn.executemany("INSERT INTO pelt_benchmark_bulk (value) VALUES ($1)", values)
        elapsed = time.perf_counter() - started
        count_row = await conn.fetchrow("SELECT count(*)::int8 AS count FROM pelt_benchmark_bulk")
    finally:
        await conn.close()
    if count_row is None or count_row["count"] != rows:
        msg = f"executemany integrity failure: expected {rows} inserted rows"
        raise RuntimeError(msg)
    return {
        "name": "sequential_executemany",
        "rows": rows,
        "elapsed_s": round(elapsed, 6),
        "rows_per_second": round(rows / elapsed, 3),
    }


def build_report(
    *,
    environment: dict[str, Any],
    config: dict[str, Any],
    aggregate_queries: list[dict[str, Any]],
    single_stream: dict[str, Any],
    executemany_loop: dict[str, Any],
) -> dict[str, Any]:
    """Build the versioned artifact and calculate observed scaling."""
    baseline = next(
        (item["queries_per_second"] for item in aggregate_queries if item["concurrency"] == 1),
        None,
    )
    if baseline is None or baseline <= 0:
        msg = "aggregate query results require a positive concurrency=1 baseline"
        raise ValueError(msg)
    scaled = [
        {
            **item,
            "speedup_vs_one": round(item["queries_per_second"] / baseline, 3),
        }
        for item in aggregate_queries
    ]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "suite": "pelt-live-postgresql",
        "captured_at": datetime.now(UTC).isoformat(),
        "source": _source_revision(),
        "environment": environment,
        "config": config,
        "workloads": {
            "aggregate_queries": scaled,
            "single_stream": single_stream,
            "executemany_loop": executemany_loop,
        },
        "caveats": [
            "Synthetic loopback benchmark; not a production capacity claim.",
            "Aggregate queries use one checked-out connection per worker and exclude pool setup.",
            "One server cursor is ordered and does not scale with pool size.",
            "executemany is a sequential convenience loop, not COPY or protocol pipelining.",
            "Compare runs only when PostgreSQL, Python, hardware, and configuration match.",
        ],
    }


async def run_pelt_benchmarks(
    dsn: str,
    *,
    concurrency: tuple[int, ...] = DEFAULT_CONCURRENCY,
    queries: int = DEFAULT_QUERIES,
    warmup: int = DEFAULT_WARMUP,
    stream_rows: int = DEFAULT_STREAM_ROWS,
    stream_batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    bulk_rows: int = DEFAULT_BULK_ROWS,
) -> dict[str, Any]:
    """Run all Pelt workloads and return a JSON-serializable artifact."""
    if not concurrency or concurrency[0] != 1:
        msg = "concurrency must contain a concurrency=1 baseline"
        raise ValueError(msg)
    if any(current <= previous for previous, current in pairwise(concurrency)):
        msg = "concurrency values must be unique and strictly increasing"
        raise ValueError(msg)
    if queries < max(concurrency):
        msg = f"queries ({queries}) must be >= maximum concurrency ({max(concurrency)})"
        raise ValueError(msg)
    if warmup < 0 or stream_rows < 1 or stream_batch_size < 1 or bulk_rows < 1:
        msg = "warmup must be >= 0 and stream/batch/bulk counts must be >= 1"
        raise ValueError(msg)

    server_version = await _server_version(dsn)
    aggregate = [
        await measure_aggregate_queries(
            dsn,
            total_queries=queries,
            concurrency=level,
            warmup=warmup,
        )
        for level in concurrency
    ]
    stream = await measure_single_stream(
        dsn,
        rows=stream_rows,
        batch_size=stream_batch_size,
    )
    bulk = await measure_executemany_loop(dsn, rows=bulk_rows)
    environment = {
        "python": _python_metadata(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "postgresql": {"server_version": server_version},
        "packages": {
            "bengal-chirp": _package_version("bengal-chirp"),
            "bengal-pounce": _package_version("bengal-pounce"),
        },
    }
    config = {
        "concurrency": list(concurrency),
        "queries_per_level": queries,
        "warmup_per_connection": warmup,
        "stream_rows": stream_rows,
        "stream_batch_size": stream_batch_size,
        "bulk_rows": bulk_rows,
        "timer": "time.perf_counter",
    }
    return build_report(
        environment=environment,
        config=config,
        aggregate_queries=aggregate,
        single_stream=stream,
        executemany_loop=bulk,
    )


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def _main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Pelt against live PostgreSQL")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("CHIRP_BENCH_PG_DSN"),
        help="Disposable PostgreSQL DSN (or set CHIRP_BENCH_PG_DSN)",
    )
    parser.add_argument(
        "--concurrency",
        type=parse_concurrency,
        default=DEFAULT_CONCURRENCY,
        help="Increasing comma-separated levels starting at 1 (default: 1,2,4,8)",
    )
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERIES)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--stream-rows", type=int, default=DEFAULT_STREAM_ROWS)
    parser.add_argument("--stream-batch-size", type=int, default=DEFAULT_STREAM_BATCH_SIZE)
    parser.add_argument("--bulk-rows", type=int, default=DEFAULT_BULK_ROWS)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(".benchmarks/pelt-latest.json"),
    )
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("--dsn or CHIRP_BENCH_PG_DSN is required")

    report = await run_pelt_benchmarks(
        args.dsn,
        concurrency=args.concurrency,
        queries=args.queries,
        warmup=args.warmup,
        stream_rows=args.stream_rows,
        stream_batch_size=args.stream_batch_size,
        bulk_rows=args.bulk_rows,
    )
    write_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nBenchmark artifact written to {args.output}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()

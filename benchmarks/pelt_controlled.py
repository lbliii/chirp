"""Repeated, failure-accounted evidence runner for Pelt's live benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks import pelt

REPORT_SCHEMA_VERSION = 1
DEFAULT_REPETITIONS = 5
README_RESULT_START = "<!-- pelt-controlled-result:start -->"
README_RESULT_END = "<!-- pelt-controlled-result:end -->"


def _rounded(value: float) -> float:
    return round(value, 3)


def _sample_summary(values: list[float]) -> dict[str, float | int]:
    """Describe successful samples without hiding run-to-run variance."""
    if not values:
        msg = "at least one successful sample is required"
        raise ValueError(msg)
    mean = statistics.mean(values)
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "samples": len(values),
        "median": _rounded(statistics.median(values)),
        "mean": _rounded(mean),
        "stdev": _rounded(deviation),
        "coefficient_of_variation": _rounded(deviation / mean) if mean else 0.0,
        "min": _rounded(min(values)),
        "max": _rounded(max(values)),
    }


def _successful_reports(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [attempt["report"] for attempt in attempts if attempt["ok"]]


def build_controlled_report(
    attempts: list[dict[str, Any]],
    *,
    repetitions: int,
    postgresql_image: str,
) -> dict[str, Any]:
    """Build a versioned artifact from raw successful and failed attempts."""
    if repetitions < 2:
        msg = "controlled benchmark requires at least two repetitions"
        raise ValueError(msg)
    if len(attempts) != repetitions:
        msg = f"expected {repetitions} attempts, received {len(attempts)}"
        raise ValueError(msg)
    reports = _successful_reports(attempts)
    if not reports:
        msg = "controlled benchmark requires at least one successful attempt"
        raise ValueError(msg)

    first = reports[0]
    concurrency = first["config"]["concurrency"]
    for report in reports[1:]:
        if report["config"] != first["config"]:
            msg = "successful attempts used different benchmark configurations"
            raise ValueError(msg)
        if report["environment"] != first["environment"]:
            msg = "successful attempts used different benchmark environments"
            raise ValueError(msg)

    aggregate: list[dict[str, Any]] = []
    for level in concurrency:
        results = [
            next(
                item
                for item in report["workloads"]["aggregate_queries"]
                if item["concurrency"] == level
            )
            for report in reports
        ]
        aggregate.append(
            {
                "concurrency": level,
                "queries_per_second": _sample_summary(
                    [item["queries_per_second"] for item in results]
                ),
                "speedup_vs_one": _sample_summary([item["speedup_vs_one"] for item in results]),
            }
        )

    stream = _sample_summary(
        [report["workloads"]["single_stream"]["rows_per_second"] for report in reports]
    )
    bulk = _sample_summary(
        [report["workloads"]["executemany_loop"]["rows_per_second"] for report in reports]
    )
    failed = repetitions - len(reports)
    safe_attempts = [
        {
            "attempt": attempt["attempt"],
            "ok": attempt["ok"],
            **(
                {
                    "captured_at": attempt["report"]["captured_at"],
                    "workloads": attempt["report"]["workloads"],
                }
                if attempt["ok"]
                else {"error_type": attempt["error_type"]}
            ),
        }
        for attempt in attempts
    ]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "suite": "pelt-controlled-free-threaded",
        "captured_at": datetime.now(UTC).isoformat(),
        "source": first["source"],
        "environment": {
            **first["environment"],
            "runner": {
                "provider": "github-actions"
                if os.environ.get("GITHUB_ACTIONS") == "true"
                else "local",
                "runner_os": os.environ.get("RUNNER_OS", "unknown"),
                "runner_arch": os.environ.get("RUNNER_ARCH", "unknown"),
            },
        },
        "config": {
            **first["config"],
            "repetitions": repetitions,
            "postgresql_image": postgresql_image,
        },
        "accounting": {
            "attempted": repetitions,
            "succeeded": len(reports),
            "failed": failed,
        },
        "attempts": safe_attempts,
        "summary": {
            "aggregate_queries": aggregate,
            "single_stream_rows_per_second": stream,
            "executemany_rows_per_second": bulk,
        },
        "caveats": [
            "Synthetic loopback benchmark; not a production capacity claim.",
            "Aggregate queries use one checked-out connection per worker and exclude pool setup.",
            "The single ordered server cursor is not evidence of pool-size scaling.",
            "executemany is a sequential loop, not COPY or protocol pipelining.",
            "The result describes this recorded environment; reruns may differ on other hardware.",
        ],
    }


async def run_controlled_benchmarks(
    dsn: str,
    *,
    repetitions: int = DEFAULT_REPETITIONS,
    concurrency: tuple[int, ...] = pelt.DEFAULT_CONCURRENCY,
    queries: int = pelt.DEFAULT_QUERIES,
    warmup: int = pelt.DEFAULT_WARMUP,
    stream_rows: int = pelt.DEFAULT_STREAM_ROWS,
    stream_batch_size: int = pelt.DEFAULT_STREAM_BATCH_SIZE,
    bulk_rows: int = pelt.DEFAULT_BULK_ROWS,
    postgresql_image: str = "unknown",
) -> dict[str, Any]:
    """Run repeated fixed-configuration attempts and retain failure accounting."""
    if sys._is_gil_enabled():
        msg = "controlled Pelt evidence must run on free-threaded Python with the GIL disabled"
        raise RuntimeError(msg)
    if repetitions < 2:
        msg = "controlled benchmark requires at least two repetitions"
        raise ValueError(msg)

    attempts: list[dict[str, Any]] = []
    for attempt_number in range(1, repetitions + 1):
        try:
            report = await pelt.run_pelt_benchmarks(
                dsn,
                concurrency=concurrency,
                queries=queries,
                warmup=warmup,
                stream_rows=stream_rows,
                stream_batch_size=stream_batch_size,
                bulk_rows=bulk_rows,
            )
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_number,
                    "ok": False,
                    "error_type": type(exc).__name__,
                }
            )
        else:
            attempts.append({"attempt": attempt_number, "ok": True, "report": report})
    return build_controlled_report(
        attempts,
        repetitions=repetitions,
        postgresql_image=postgresql_image,
    )


def render_controlled_result(report: dict[str, Any], *, artifact_link: str) -> str:
    """Render source documentation directly from a controlled artifact."""
    environment = report["environment"]
    python = environment["python"]
    postgresql = environment["postgresql"]
    config = report["config"]
    accounting = report["accounting"]
    aggregate = report["summary"]["aggregate_queries"]
    baseline = aggregate[0]
    highest = aggregate[-1]
    gil_mode = "GIL disabled" if python["free_threaded"] else "GIL enabled"
    concurrency_arg = ",".join(str(value) for value in config["concurrency"])
    command = (
        "uv run --python 3.14.2t python -m benchmarks.pelt_controlled "
        f"--repetitions {config['repetitions']} --concurrency {concurrency_arg} "
        f"--queries {config['queries_per_level']} --warmup {config['warmup_per_connection']} "
        f"--stream-rows {config['stream_rows']} "
        f"--stream-batch-size {config['stream_batch_size']} "
        f"--bulk-rows {config['bulk_rows']} --output benchmarks/{artifact_link}"
    )
    lines = [
        "### Committed controlled result",
        "",
        (
            f"Captured {str(report['captured_at'])[:10]} on {environment['machine']} "
            f"({environment['processor']}) with {python['implementation']} {python['version']} "
            f"({gil_mode}) and PostgreSQL {postgresql['server_version']} "
            f"from `{config['postgresql_image']}`. "
            f"{accounting['succeeded']} of {accounting['attempted']} attempts succeeded. "
            f"[Full artifact]({artifact_link})."
        ),
        "",
        f"Reproduce from the repository root: `{command}`",
        "",
        "| Connections | Median queries/s | QPS CV | Median speedup vs 1 | Speedup CV |",
        "|---:|---:|---:|---:|---:|",
    ]
    for item in aggregate:
        qps = item["queries_per_second"]
        speedup = item["speedup_vs_one"]
        lines.append(
            f"| {item['concurrency']} | {qps['median']:.1f} | "
            f"{qps['coefficient_of_variation']:.3f} | {speedup['median']:.3f}x | "
            f"{speedup['coefficient_of_variation']:.3f} |"
        )
    stream = report["summary"]["single_stream_rows_per_second"]
    bulk = report["summary"]["executemany_rows_per_second"]
    lines.extend(
        [
            "",
            (
                f"Observed aggregate prepared-query throughput changed from "
                f"{baseline['queries_per_second']['median']:.1f} queries/s at one connection "
                f"to {highest['queries_per_second']['median']:.1f} queries/s at "
                f"{highest['concurrency']} connections "
                f"({highest['speedup_vs_one']['median']:.3f}x median)."
            ),
            "",
            (
                f"The separate single ordered stream measured {stream['median']:.1f} rows/s "
                f"median (CV {stream['coefficient_of_variation']:.3f}); the sequential "
                f"`executemany` loop measured {bulk['median']:.1f} rows/s median "
                f"(CV {bulk['coefficient_of_variation']:.3f}). Neither boundary is a "
                "pool-scaling result. This loopback evidence is not a production-capacity claim."
            ),
        ]
    )
    return "\n".join(lines)


def update_readme_result(readme: Path, rendered: str) -> None:
    """Replace the controlled-result section between stable README markers."""
    content = readme.read_text(encoding="utf-8")
    if README_RESULT_START not in content or README_RESULT_END not in content:
        msg = f"{readme} is missing controlled Pelt result markers"
        raise ValueError(msg)
    before, remainder = content.split(README_RESULT_START, 1)
    _old, after = remainder.split(README_RESULT_END, 1)
    replacement = f"{README_RESULT_START}\n{rendered}\n{README_RESULT_END}"
    readme.write_text(f"{before}{replacement}{after}", encoding="utf-8")


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _update_readme_from_artifact(artifact: Path, readme: Path) -> None:
    report = json.loads(artifact.read_text(encoding="utf-8"))
    artifact_link = os.path.relpath(artifact, readme.parent)
    update_readme_result(
        readme,
        render_controlled_result(report, artifact_link=Path(artifact_link).as_posix()),
    )


async def _main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run controlled Pelt scaling evidence")
    parser.add_argument("--dsn", default=os.environ.get("CHIRP_BENCH_PG_DSN"))
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument(
        "--concurrency", type=pelt.parse_concurrency, default=pelt.DEFAULT_CONCURRENCY
    )
    parser.add_argument("--queries", type=int, default=pelt.DEFAULT_QUERIES)
    parser.add_argument("--warmup", type=int, default=pelt.DEFAULT_WARMUP)
    parser.add_argument("--stream-rows", type=int, default=pelt.DEFAULT_STREAM_ROWS)
    parser.add_argument("--stream-batch-size", type=int, default=pelt.DEFAULT_STREAM_BATCH_SIZE)
    parser.add_argument("--bulk-rows", type=int, default=pelt.DEFAULT_BULK_ROWS)
    parser.add_argument(
        "--postgresql-image", default=os.environ.get("CHIRP_BENCH_PG_IMAGE", "unknown")
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path(".benchmarks/pelt-controlled.json")
    )
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--render-artifact", type=Path)
    args = parser.parse_args(argv)

    if args.render_artifact is not None:
        if args.readme is None:
            parser.error("--render-artifact requires --readme")
        _update_readme_from_artifact(args.render_artifact, args.readme)
        return 0
    if not args.dsn:
        parser.error("--dsn or CHIRP_BENCH_PG_DSN is required")

    report = await run_controlled_benchmarks(
        args.dsn,
        repetitions=args.repetitions,
        concurrency=args.concurrency,
        queries=args.queries,
        warmup=args.warmup,
        stream_rows=args.stream_rows,
        stream_batch_size=args.stream_batch_size,
        bulk_rows=args.bulk_rows,
        postgresql_image=args.postgresql_image,
    )
    write_report(report, args.output)
    if args.readme is not None:
        _update_readme_from_artifact(args.output, args.readme)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nControlled benchmark artifact written to {args.output}")
    return 1 if report["accounting"]["failed"] else 0


def main() -> None:
    raise SystemExit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()

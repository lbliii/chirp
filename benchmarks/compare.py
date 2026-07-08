"""Compare Chirp core benchmark reports and enforce a regression budget.

Reports should be produced sequentially on the same CI runner. This is an
internal regression signal, not cross-framework performance evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_METRIC = "p50_us"
DEFAULT_WARNING_PERCENT = 5.0
DEFAULT_FAILURE_PERCENT = 20.0
COMMENT_MARKER = "<!-- chirp-core-benchmark-comparison -->"


class BenchmarkReportError(ValueError):
    """A benchmark report cannot be compared safely."""


@dataclass(frozen=True, slots=True)
class Comparison:
    """One workload comparison."""

    name: str
    baseline_us: float | None
    candidate_us: float
    change_percent: float | None
    status: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """The complete comparison and gate decision."""

    comparisons: tuple[Comparison, ...]
    missing_workloads: tuple[str, ...]
    regression_workloads: tuple[str, ...]
    metric: str
    warning_percent: float
    failure_percent: float

    @property
    def failed(self) -> bool:
        """Return whether the candidate exceeds the regression contract."""
        return bool(self.missing_workloads or self.regression_workloads)


def load_report(path: Path) -> dict[str, Any]:
    """Load and minimally validate one core benchmark report."""
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise BenchmarkReportError(f"Benchmark report {path} must contain a JSON object.")
    if report.get("schema_version") != 1 or report.get("suite") != "chirp-core":
        raise BenchmarkReportError(f"Benchmark report {path} must use chirp-core schema version 1.")
    if not isinstance(report.get("workloads"), list):
        raise BenchmarkReportError(f"Benchmark report {path} must contain a workloads list.")
    return report


def _workloads(report: dict[str, Any], *, metric: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for workload in report["workloads"]:
        if not isinstance(workload, dict) or not isinstance(workload.get("name"), str):
            raise BenchmarkReportError(
                "Every benchmark workload must be an object with a string name."
            )
        name = workload["name"]
        value = workload.get(metric)
        if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
            raise BenchmarkReportError(
                f"Benchmark workload {name!r} must contain a positive numeric {metric}."
            )
        if name in values:
            raise BenchmarkReportError(f"Benchmark workload {name!r} appears more than once.")
        values[name] = float(value)
    return values


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    metric: str = DEFAULT_METRIC,
    warning_percent: float = DEFAULT_WARNING_PERCENT,
    failure_percent: float = DEFAULT_FAILURE_PERCENT,
) -> ComparisonResult:
    """Compare reports and classify changes against documented thresholds."""
    if warning_percent < 0 or failure_percent <= warning_percent:
        raise BenchmarkReportError(
            "Benchmark thresholds require 0 <= warning-percent < failure-percent."
        )
    for field in ("iterations", "route_count", "units"):
        baseline_value = baseline.get("config", {}).get(field)
        candidate_value = candidate.get("config", {}).get(field)
        if baseline_value != candidate_value:
            raise BenchmarkReportError(
                f"Benchmark config {field!r} must match; "
                f"base={baseline_value!r}, candidate={candidate_value!r}."
            )
    baseline_values = _workloads(baseline, metric=metric)
    candidate_values = _workloads(candidate, metric=metric)
    missing = tuple(sorted(baseline_values.keys() - candidate_values.keys()))
    regressions: list[str] = []
    comparisons: list[Comparison] = []

    for name in sorted(candidate_values):
        current = candidate_values[name]
        previous = baseline_values.get(name)
        if previous is None:
            comparisons.append(Comparison(name, None, current, None, "new"))
            continue
        change = ((current - previous) / previous) * 100
        if change > failure_percent:
            status = "regression"
            regressions.append(name)
        elif change > warning_percent:
            status = "warning"
        elif change < -warning_percent:
            status = "improvement"
        else:
            status = "stable"
        comparisons.append(Comparison(name, previous, current, change, status))

    return ComparisonResult(
        comparisons=tuple(comparisons),
        missing_workloads=missing,
        regression_workloads=tuple(regressions),
        metric=metric,
        warning_percent=warning_percent,
        failure_percent=failure_percent,
    )


def _runtime_label(report: dict[str, Any]) -> str:
    python = report.get("environment", {}).get("python", {})
    version = python.get("version", "unknown")
    cache_tag = python.get("cache_tag", "unknown")
    mode = "free-threaded" if python.get("free_threaded") else "GIL-enabled"
    return f"CPython {version} ({cache_tag}, {mode})"


def render_markdown(
    result: ComparisonResult,
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    """Render a stable PR comment and Actions summary."""
    labels = {
        "new": "new",
        "regression": "FAIL",
        "warning": "warn",
        "improvement": "faster",
        "stable": "stable",
    }
    lines = [
        COMMENT_MARKER,
        "## Core benchmark comparison",
        "",
        (
            "Synthetic in-process regression workloads run sequentially on the same "
            "GitHub-hosted runner. These numbers are not production or cross-framework evidence."
        ),
        "",
        "| Workload | Base p50 | Candidate p50 | Change | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for item in result.comparisons:
        baseline_value = "—" if item.baseline_us is None else f"{item.baseline_us:.3f} µs"
        change = "—" if item.change_percent is None else f"{item.change_percent:+.1f}%"
        lines.append(
            f"| `{item.name}` | {baseline_value} | {item.candidate_us:.3f} µs | "
            f"{change} | {labels[item.status]} |"
        )

    if result.missing_workloads:
        names = ", ".join(f"`{name}`" for name in result.missing_workloads)
        lines.extend(["", f"**Gate failure:** candidate omitted baseline workload(s): {names}."])
    if result.regression_workloads:
        names = ", ".join(f"`{name}`" for name in result.regression_workloads)
        lines.extend(
            [
                "",
                (
                    f"**Gate failure:** {names} exceeded the "
                    f"{result.failure_percent:g}% p50 regression budget."
                ),
            ]
        )
    if not result.failed:
        lines.extend(["", "**Gate passed:** no workload exceeded the regression budget."])

    lines.extend(
        [
            "",
            (
                f"Warnings begin above {result.warning_percent:g}%; CI fails above "
                f"{result.failure_percent:g}%. Metric: `{result.metric}`."
            ),
            f"Base: {_runtime_label(baseline)}. Candidate: {_runtime_label(candidate)}.",
        ]
    )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--metric", default=DEFAULT_METRIC)
    parser.add_argument("--warning-percent", type=float, default=DEFAULT_WARNING_PERCENT)
    parser.add_argument("--failure-percent", type=float, default=DEFAULT_FAILURE_PERCENT)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        baseline = load_report(args.baseline)
        candidate = load_report(args.candidate)
        result = compare_reports(
            baseline,
            candidate,
            metric=args.metric,
            warning_percent=args.warning_percent,
            failure_percent=args.failure_percent,
        )
    except (BenchmarkReportError, json.JSONDecodeError, OSError) as exc:
        print(f"Benchmark comparison failed: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(result, baseline=baseline, candidate=candidate)
    print(markdown, end="")
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    return int(result.failed)


if __name__ == "__main__":
    raise SystemExit(main())

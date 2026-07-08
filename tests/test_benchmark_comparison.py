"""Regression proof for the core benchmark CI gate (#620)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_COMPARE_PATH = ROOT / "benchmarks" / "compare.py"
_SPEC = importlib.util.spec_from_file_location("benchmarks.compare", _COMPARE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_COMPARE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _COMPARE
_SPEC.loader.exec_module(_COMPARE)

COMMENT_MARKER = _COMPARE.COMMENT_MARKER
aggregate_reports = _COMPARE.aggregate_reports
compare_reports = _COMPARE.compare_reports
render_markdown = _COMPARE.render_markdown


def _report(values: dict[str, float]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "suite": "chirp-core",
        "environment": {
            "python": {
                "version": "3.14.2",
                "cache_tag": "cpython-314t",
                "free_threaded": True,
            }
        },
        "config": {"iterations": 500, "route_count": 100, "units": "microseconds"},
        "workloads": [
            {"name": name, "p50_us": value, "avg_us": value, "p99_us": value}
            for name, value in values.items()
        ],
    }


def test_comparison_classifies_stable_warning_improvement_and_new_workloads() -> None:
    baseline = _report({"stable": 100.0, "warning": 100.0, "faster": 100.0})
    candidate = _report({"stable": 103.0, "warning": 110.0, "faster": 80.0, "new": 5.0})

    result = compare_reports(baseline, candidate)

    assert not result.failed
    assert {item.name: item.status for item in result.comparisons} == {
        "faster": "improvement",
        "new": "new",
        "stable": "stable",
        "warning": "warning",
    }
    markdown = render_markdown(result, baseline=baseline, candidate=candidate)
    assert markdown.startswith(COMMENT_MARKER)
    assert "Gate passed" in markdown


def test_comparison_fails_for_regressions_and_removed_workloads() -> None:
    result = compare_reports(
        _report({"removed": 10.0, "slow": 10.0}),
        _report({"slow": 12.1}),
    )

    assert result.failed
    assert result.missing_workloads == ("removed",)
    assert result.regression_workloads == ("slow",)


def test_comparison_rejects_mismatched_workload_configuration() -> None:
    baseline = _report({"render": 10.0})
    candidate = _report({"render": 10.0})
    config = candidate["config"]
    assert isinstance(config, dict)
    config["route_count"] = 10

    with pytest.raises(ValueError, match=r"route_count.*must match"):
        compare_reports(baseline, candidate)


def test_aggregation_uses_median_of_repeated_p50_results() -> None:
    aggregated = aggregate_reports(
        [_report({"render": 10.0}), _report({"render": 30.0}), _report({"render": 11.0})]
    )

    config = aggregated["config"]
    assert isinstance(config, dict)
    assert config["comparison_rounds"] == 3
    assert aggregated["workloads"] == [{"name": "render", "p50_us": 11.0}]


@pytest.mark.issue(620)
def test_benchmark_comparison_cli_fails_ci_and_writes_pr_summary(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    summary = tmp_path / "comparison.md"
    baseline.write_text(json.dumps(_report({"render": 10.0})), encoding="utf-8")
    candidate.write_text(json.dumps(_report({"render": 13.0})), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--markdown-output",
            str(summary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Gate failure" in summary.read_text(encoding="utf-8")
    assert "render" in result.stdout

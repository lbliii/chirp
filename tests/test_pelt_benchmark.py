"""Schema and CLI proof for the live Pelt benchmark harness (#260)."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PELT_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "pelt.py"
_CONTROLLED_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "pelt_controlled.py"
_CI_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_BENCHMARKS_CI_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "benchmarks.yml"
)
_SPEC = importlib.util.spec_from_file_location("benchmarks.pelt", _PELT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_PELT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PELT
_SPEC.loader.exec_module(_PELT)
sys.path.insert(0, str(_CONTROLLED_PATH.parents[1]))
try:
    _CONTROLLED = importlib.import_module("benchmarks.pelt_controlled")
finally:
    sys.path.pop(0)


@pytest.mark.issue(260)
def test_pelt_concurrency_parser_and_allocation() -> None:
    assert _PELT.parse_concurrency("1,2,4,8") == (1, 2, 4, 8)
    assert _PELT.allocate_queries(10, 3) == (4, 3, 3)

    for invalid in ("", "0,1", "2,4", "1,1", "1,4,2", "one,two"):
        with pytest.raises(argparse.ArgumentTypeError):
            _PELT.parse_concurrency(invalid)


@pytest.mark.issue(260)
def test_pelt_report_keeps_scaling_and_boundaries_separate(tmp_path: Path) -> None:
    report = _PELT.build_report(
        environment={"python": {"free_threaded": True}, "postgresql": {"server_version": "18"}},
        config={"concurrency": [1, 2]},
        aggregate_queries=[
            {"concurrency": 1, "queries_per_second": 100.0},
            {"concurrency": 2, "queries_per_second": 175.0},
        ],
        single_stream={"name": "single_server_cursor", "rows_per_second": 50.0},
        executemany_loop={"name": "sequential_executemany", "rows_per_second": 25.0},
    )

    assert report["schema_version"] == 1
    assert report["suite"] == "pelt-live-postgresql"
    aggregate = report["workloads"]["aggregate_queries"]
    assert [item["speedup_vs_one"] for item in aggregate] == [1.0, 1.75]
    assert report["workloads"]["single_stream"]["name"] == "single_server_cursor"
    assert report["workloads"]["executemany_loop"]["name"] == "sequential_executemany"
    assert any("not a production capacity claim" in caveat for caveat in report["caveats"])

    output = tmp_path / "pelt.json"
    _PELT.write_report(report, output)
    assert json.loads(output.read_text()) == report


@pytest.mark.issue(260)
def test_pelt_benchmark_cli_requires_an_explicit_dsn() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "benchmarks.pelt", "--queries", "8"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CHIRP_BENCH_PG_DSN": ""},
    )

    assert result.returncode == 2
    assert "--dsn or CHIRP_BENCH_PG_DSN is required" in result.stderr


@pytest.mark.issue(260)
def test_live_postgres_ci_smokes_the_pelt_benchmark() -> None:
    workflow = _CI_PATH.read_text()

    assert "name: Pelt benchmark smoke" in workflow
    assert "CHIRP_BENCH_PG_DSN" in workflow
    assert "python -m benchmarks.pelt" in workflow
    assert "--concurrency 1,2" in workflow
    assert "--output /tmp/pelt-smoke.json" in workflow


@pytest.mark.issue(692)
def test_pelt_software_provenance_includes_every_installed_distribution() -> None:
    packages = _PELT._installed_packages()

    assert list(packages) == sorted(packages, key=str.casefold)
    assert {"anyio", "bengal-chirp", "bengal-pounce"} <= packages.keys()


def _pelt_attempt(attempt: int, qps: tuple[float, float], *, stream: float, bulk: float):
    report = _PELT.build_report(
        environment={
            "python": {
                "implementation": "CPython",
                "version": "3.14.2",
                "free_threaded": True,
            },
            "machine": "x86_64",
            "processor": "test CPU",
            "postgresql": {"server_version": "18.1"},
        },
        config={
            "concurrency": [1, 2],
            "queries_per_level": 100,
            "warmup_per_connection": 1,
            "stream_rows": 10,
            "stream_batch_size": 5,
            "bulk_rows": 4,
            "timer": "time.perf_counter",
        },
        aggregate_queries=[
            {"concurrency": 1, "queries_per_second": qps[0]},
            {"concurrency": 2, "queries_per_second": qps[1]},
        ],
        single_stream={"name": "single_server_cursor", "rows_per_second": stream},
        executemany_loop={"name": "sequential_executemany", "rows_per_second": bulk},
    )
    report["source"] = {"commit": "abc123", "dirty": False}
    report["captured_at"] = f"2026-07-14T00:00:0{attempt}+00:00"
    return {"attempt": attempt, "ok": True, "report": report}


@pytest.mark.issue(692)
def test_controlled_pelt_report_preserves_attempts_failures_and_variance() -> None:
    report = _CONTROLLED.build_controlled_report(
        [
            _pelt_attempt(1, (100.0, 150.0), stream=50.0, bulk=25.0),
            _pelt_attempt(2, (120.0, 180.0), stream=60.0, bulk=30.0),
            {"attempt": 3, "ok": False, "error_type": "TimeoutError"},
        ],
        repetitions=3,
        postgresql_image="postgres:18.1-bookworm",
    )

    assert report["schema_version"] == 1
    assert report["suite"] == "pelt-controlled-free-threaded"
    assert report["accounting"] == {"attempted": 3, "succeeded": 2, "failed": 1}
    assert report["attempts"][2] == {
        "attempt": 3,
        "ok": False,
        "error_type": "TimeoutError",
    }
    aggregate = report["summary"]["aggregate_queries"]
    assert aggregate[0]["queries_per_second"]["median"] == 110.0
    assert aggregate[0]["queries_per_second"]["stdev"] == 14.142
    assert aggregate[1]["speedup_vs_one"]["median"] == 1.5
    assert report["summary"]["single_stream_rows_per_second"]["median"] == 55.0


@pytest.mark.issue(692)
def test_controlled_pelt_readme_is_generated_and_keeps_boundaries_caveated(
    tmp_path: Path,
) -> None:
    report = _CONTROLLED.build_controlled_report(
        [
            _pelt_attempt(1, (100.0, 150.0), stream=50.0, bulk=25.0),
            _pelt_attempt(2, (120.0, 180.0), stream=60.0, bulk=30.0),
        ],
        repetitions=2,
        postgresql_image="postgres:18.1-bookworm",
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        f"before\n{_CONTROLLED.README_RESULT_START}\nold\n{_CONTROLLED.README_RESULT_END}\nafter\n",
        encoding="utf-8",
    )

    rendered = _CONTROLLED.render_controlled_result(
        report, artifact_link="results/pelt-controlled.json"
    )
    _CONTROLLED.update_readme_result(readme, rendered)
    updated = readme.read_text(encoding="utf-8")

    assert "| 2 | 165.0" in updated
    assert "1.500x" in updated
    assert "single ordered stream" in updated
    assert "Neither boundary is a pool-scaling result" in updated
    assert "not a production-capacity claim" in updated
    assert "old" not in updated


@pytest.mark.issue(692)
def test_controlled_pelt_ci_pins_environment_and_uploads_raw_evidence() -> None:
    workflow = _BENCHMARKS_CI_PATH.read_text(encoding="utf-8")

    assert "name: Run controlled Pelt evidence" in workflow
    assert 'python-version: "3.14.2t"' in workflow
    assert "postgres:18.1-bookworm" in workflow
    assert "uv sync --no-sources --group dev --extra data-pg" in workflow
    assert "--repetitions 5" in workflow
    assert "--concurrency 1,2,4,8" in workflow
    assert "benchmark-artifacts/pelt-controlled.json" in workflow
    assert "actions/upload-artifact@v7" in workflow

"""Schema and CLI proof for the live Pelt benchmark harness (#260)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PELT_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "pelt.py"
_CI_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_SPEC = importlib.util.spec_from_file_location("benchmarks.pelt", _PELT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_PELT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PELT
_SPEC.loader.exec_module(_PELT)


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

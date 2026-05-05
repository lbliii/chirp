"""Smoke tests for the core benchmark harness."""

import importlib.util
from pathlib import Path

import pytest

_CORE_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "core.py"
_RUN_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "run.py"
_SPEC = importlib.util.spec_from_file_location("benchmarks.core", _CORE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_CORE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CORE)
_RUN_SPEC = importlib.util.spec_from_file_location("benchmarks.run", _RUN_PATH)
assert _RUN_SPEC is not None
assert _RUN_SPEC.loader is not None
_RUN = importlib.util.module_from_spec(_RUN_SPEC)
_RUN_SPEC.loader.exec_module(_RUN)


@pytest.mark.asyncio
async def test_core_benchmarks_return_reproducible_json_shape(tmp_path: Path) -> None:
    report = await _CORE.run_core_benchmarks(iterations=2, route_count=2)

    assert report["schema_version"] == 1
    assert report["suite"] == "chirp-core"
    assert report["config"]["iterations"] == 2
    assert report["environment"]["python"]["version"]

    workloads = {item["name"]: item for item in report["workloads"]}
    assert set(workloads) == {
        "template_render",
        "fragment_render",
        "oob_serialization",
        "suspense_first_chunk",
        "sse_fanout",
        "filesystem_route_dispatch",
    }
    for workload in workloads.values():
        assert workload["iterations"] == 2
        assert workload["avg_us"] >= 0
        assert workload["p50_us"] >= 0
        assert workload["p99_us"] >= 0

    assert (
        workloads["sse_fanout"]["events_delivered"]
        == workloads["sse_fanout"]["expected_deliveries"]
    )

    output = tmp_path / "core.json"
    _CORE.write_report(report, output)
    assert output.read_text(encoding="utf-8").startswith("{\n")


def test_networked_benchmarks_include_template_workload() -> None:
    assert _RUN.NETWORKED_WORKLOADS == (
        ("json", "/json"),
        ("cpu", "/cpu"),
        ("template", "/template"),
    )

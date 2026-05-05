"""Smoke tests for the core benchmark harness."""

import importlib.util
from pathlib import Path

import pytest

_CORE_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "core.py"
_RUN_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "run.py"
_WORKLOADS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "apps" / "workloads.py"
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
_WORKLOADS_SPEC = importlib.util.spec_from_file_location(
    "benchmarks.apps.workloads",
    _WORKLOADS_PATH,
)
assert _WORKLOADS_SPEC is not None
assert _WORKLOADS_SPEC.loader is not None
_WORKLOADS = importlib.util.module_from_spec(_WORKLOADS_SPEC)
_WORKLOADS_SPEC.loader.exec_module(_WORKLOADS)


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


def test_networked_benchmarks_include_full_workload_matrix() -> None:
    assert _RUN.NETWORKED_WORKLOADS == (
        ("json", "/json"),
        ("cpu", "/cpu"),
        ("db", "/db"),
        ("template", "/template"),
    )


def test_networked_benchmarks_include_full_framework_matrix() -> None:
    assert _RUN.DEFAULT_TARGETS == ["chirp", "fastapi", "flask", "starlette", "litestar"]
    assert set(_RUN.DEFAULT_TARGETS).issubset(_RUN.ALL_FRAMEWORKS)


def test_networked_benchmarks_record_python_gil_mode() -> None:
    metadata = _RUN.python_runtime_metadata()

    assert metadata["version"]
    assert metadata["implementation"]
    assert metadata["cache_tag"]
    assert isinstance(metadata["gil_enabled"], bool)
    assert metadata["free_threaded"] is (not metadata["gil_enabled"])
    assert "GIL" in _RUN.python_runtime_label()


def test_networked_db_workload_returns_stable_rows() -> None:
    rows = _WORKLOADS.fetch_db_rows()

    assert len(rows) == _WORKLOADS.DB_QUERY_LIMIT
    assert rows[0] == {"id": 100, "name": "Row 100", "score": 700}
    assert rows[-1]["score"] < rows[0]["score"]

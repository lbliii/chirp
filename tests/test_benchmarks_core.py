"""Smoke tests for the core benchmark harness."""

import importlib.util
import json
import subprocess
import sys
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


def test_core_benchmark_imports_in_a_clean_process() -> None:
    """The release benchmark must not depend on pytest's import order."""
    subprocess.run(
        [sys.executable, "-c", "from chirp.server.negotiation import negotiate"],
        cwd=_CORE_PATH.parents[1],
        check=True,
        capture_output=True,
        text=True,
    )


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
    assert _RUN.DEFAULT_TARGETS == [
        "chirp",
        "fasthtml",
        "fastapi",
        "flask",
        "starlette",
        "litestar",
    ]
    assert set(_RUN.DEFAULT_TARGETS).issubset(_RUN.ALL_FRAMEWORKS)


@pytest.mark.issue(621)
def test_fasthtml_benchmark_uses_native_ft_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fasthtml")
    monkeypatch.syspath_prepend(str(_CORE_PATH.parents[1]))
    from starlette.testclient import TestClient

    from benchmarks.apps.fasthtml_app import app

    with TestClient(app) as client:
        json_response = client.get("/json")
        template_response = client.get("/template")

    assert json_response.json() == {"message": "hello", "count": 42}
    assert template_response.status_code == 200
    assert template_response.text.startswith("<main>")
    assert "Benchmark Items" in template_response.text
    assert template_response.text.count("<li>") == 20


def test_networked_benchmarks_record_python_gil_mode() -> None:
    metadata = _RUN.python_runtime_metadata()

    assert metadata["version"]
    assert metadata["implementation"]
    assert metadata["cache_tag"]
    assert isinstance(metadata["gil_enabled"], bool)
    assert metadata["free_threaded"] is (not metadata["gil_enabled"])
    assert "GIL" in _RUN.python_runtime_label()


@pytest.mark.issue(621)
def test_networked_report_is_versioned_and_preserves_failures(tmp_path: Path) -> None:
    results = [
        _RUN.BenchResult(
            framework="chirp",
            workload="json",
            ok=9,
            failed=1,
            total=10,
            req_per_sec=123.45,
            avg_ms=8.0,
            p50_ms=7.0,
            p99_ms=20.0,
            rounds=3,
        )
    ]

    report = _RUN.build_network_report(
        results,
        targets=["chirp"],
        concurrency=10,
        client_strategy="shared-limits",
    )
    output = tmp_path / "network.json"
    _RUN.write_network_report(report, output)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert written["schema_version"] == 1
    assert written["suite"] == "chirp-networked-framework-comparison"
    assert written["config"]["concurrency"] == 10
    assert written["results"][0]["failed"] == 1
    assert written["environment"]["packages"]["bengal-chirp"]


@pytest.mark.issue(621)
def test_networked_readme_table_is_generated_from_report(tmp_path: Path) -> None:
    report = {
        "captured_at": "2026-07-08T00:00:00+00:00",
        "environment": {
            "machine": "test-machine",
            "python": {
                "implementation": "CPython",
                "version": "3.14.0",
                "free_threaded": True,
            },
        },
        "config": {
            "requests_per_round": 10,
            "rounds": 3,
            "concurrency": 2,
            "workers": 1,
            "client_strategy": "shared-limits",
            "targets": ["chirp"],
            "workloads": ["json", "cpu", "db", "template"],
        },
        "results": [
            {
                "framework": "chirp",
                "workload": workload,
                "failed": 1 if workload == "db" else 0,
                "req_per_sec": 100.0,
                "p50_ms": 5.0,
            }
            for workload in ("json", "cpu", "db", "template")
        ],
    }
    readme = tmp_path / "README.md"
    readme.write_text(
        f"before\n{_RUN.README_BASELINE_START}\nold\n{_RUN.README_BASELINE_END}\nafter\n",
        encoding="utf-8",
    )

    table = _RUN.render_baseline_table(report, artifact_link="results/network.json")
    _RUN.update_readme_baseline(readme, table)
    updated = readme.read_text(encoding="utf-8")

    assert "| chirp | 100.0 (5.0 ms)" in updated
    assert "| 1 |" in updated
    assert "[Full artifact](results/network.json)" in updated
    assert "old" not in updated


def test_networked_db_workload_returns_stable_rows() -> None:
    rows = _WORKLOADS.fetch_db_rows()

    assert len(rows) == _WORKLOADS.DB_QUERY_LIMIT
    assert rows[0] == {"id": 100, "name": "Row 100", "score": 700}
    assert rows[-1]["score"] < rows[0]["score"]

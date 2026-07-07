"""Tests for the optional pinned htmx migration-inventory wrapper."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.issue(547)


def _script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "htmx4_upgrade_check.py"
    spec = importlib.util.spec_from_file_location("htmx4_upgrade_check", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_checker_output_is_normalized_and_classified() -> None:
    script = _script()
    output = """src/chirp/a.html:12: [removed-attr] hx-ext is removed
examples/demo/app.html:4: [inheritance] hx-target needs :inherited
docs/guide.html:9: [old-event] old event name
"""
    findings = script.parse_findings(output)
    report = script.build_report(
        findings,
        "Found 3 issue(s) in 3 of 209 file(s).",
        root=Path("."),
    )

    assert report["scanned_files"] == 209
    assert report["files_with_findings"] == 3
    assert report["total_findings"] == 3
    assert report["categories"] == {
        "inheritance": 1,
        "old-event": 1,
        "removed-attr": 1,
    }
    assert report["surfaces"] == {"documentation": 1, "examples": 1, "framework": 1}


def test_repository_file_collection_excludes_local_environments(tmp_path: Path) -> None:
    script = _script()
    (tmp_path / "page.html").write_text("<main></main>", encoding="utf-8")
    (tmp_path / "notes.md").write_text("not scanned", encoding="utf-8")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "dependency.html").write_text("ignored", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.js").write_text("ignored", encoding="utf-8")

    assert script.collect_repository_files(tmp_path) == ["page.html"]


def test_findings_exit_one_is_a_successful_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="tests/page.html:2: [renamed-attr] hx-disabled-elt → hx-disable\n",
            stderr="Found 1 issue(s) in 1 of 1 file(s).\n",
        )

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    report = script.run_checker(Path("."))
    assert report["total_findings"] == 1
    assert report["surfaces"] == {"tests": 1}


def test_missing_optional_tool_has_actionable_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()

    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(script.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match=r"app.check\(\).+no Node dependency"):
        script.run_checker(Path("."))


def test_missing_upstream_summary_is_not_recorded_as_a_clean_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _script()

    def incomplete(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="npm cache was unavailable",
        )

    monkeypatch.setattr(script.subprocess, "run", incomplete)
    with pytest.raises(RuntimeError, match="no scan summary"):
        script.run_checker(Path("."))

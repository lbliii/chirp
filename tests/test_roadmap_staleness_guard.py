"""Tests for scripts/check_roadmap_staleness.py (issue #199).

The guard fails when a roadmap file statically asserts "no open GitHub issues"
without a dated-snapshot qualifier, and is a stdlib-only 0/1 exit script with no
hard network dependency (the live ``gh`` cross-check degrades to a skip).
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_roadmap_staleness.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_roadmap_staleness", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


@pytest.mark.parametrize(
    "line",
    [
        "- Open GitHub issues checked on 2026-05-30: none.",
        "- GitHub issues: none open",
        "There are no open GitHub issues right now.",
    ],
)
def test_unqualified_stale_claim_fails(tmp_path, line):
    f = tmp_path / "ROADMAP.md"
    f.write_text(f"# Roadmap\n{line}\n", encoding="utf-8")
    assert guard.main([str(f)]) == 1


@pytest.mark.parametrize(
    "line",
    [
        "- GitHub issues: none open as of the 2026-05-30 research pass.",
        "- GitHub issues: none open (point-in-time snapshot).",
        "Open issues: <https://github.com/lbliii/chirp/issues> is authoritative.",
        "The dashboard ships with zero open tickets in its demo data.",
    ],
)
def test_qualified_or_unrelated_lines_pass(tmp_path, line):
    f = tmp_path / "ROADMAP.md"
    f.write_text(f"# Roadmap\n{line}\n", encoding="utf-8")
    assert guard.main([str(f)]) == 0


def test_missing_file_is_clean(tmp_path):
    assert guard.main([str(tmp_path / "does-not-exist.md")]) == 0


def test_repo_roadmaps_are_clean():
    """The shipped ROADMAP.md and plan/roadmap.md must pass the guard."""
    files = [str(_REPO_ROOT / "ROADMAP.md"), str(_REPO_ROOT / "plan" / "roadmap.md")]
    assert guard.main(files) == 0


def test_with_gh_flag_does_not_fail_on_clean_files(tmp_path, monkeypatch):
    """--with-gh must never fail on a clean file, even when gh is unavailable."""
    monkeypatch.setattr(guard, "_gh_has_open_issues", lambda: None)
    f = tmp_path / "ROADMAP.md"
    f.write_text("# Roadmap\nLive backlog is authoritative.\n", encoding="utf-8")
    assert guard.main([str(f), "--with-gh"]) == 0

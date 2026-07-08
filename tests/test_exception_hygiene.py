"""Regression proof for the exception-hygiene CI ratchet (#620)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/lint_exception_hygiene.py"


def _run(source: Path, baseline: Path, *, write: bool = False) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--source",
        str(source),
        "--baseline",
        str(baseline),
    ]
    if write:
        command.append("--write-baseline")
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


def _empty_baseline(path: Path) -> None:
    path.write_text(json.dumps({"fingerprints": []}), encoding="utf-8")


@pytest.mark.issue(620)
def test_repository_exception_hygiene_matches_reviewed_baseline() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no exception-hygiene drift" in result.stdout


def test_gate_rejects_each_new_exception_anti_pattern(tmp_path: Path) -> None:
    source = tmp_path / "bad.py"
    source.write_text(
        """\
import contextlib

def bad_raise() -> None:
    raise ValueError("nope")

def bad_suppress() -> None:
    with contextlib.suppress(ValueError):
        pass

def bad_handler() -> None:
    try:
        int("not-a-number")
    except ValueError:
        pass

def bad_load() -> dict[str, object]:
    return load_config("settings.toml") or {}
""",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    _empty_baseline(baseline)

    result = _run(source, baseline)

    assert result.returncode == 1
    assert "raise-message" in result.stderr
    assert "exception-suppress" in result.stderr
    assert "silent-handler" in result.stderr
    assert "masked-load-fallback" in result.stderr


def test_explicit_silent_reasons_and_private_raises_are_allowed(tmp_path: Path) -> None:
    source = tmp_path / "allowed.py"
    source.write_text(
        """\
import contextlib

def _private_invariant() -> None:
    raise ValueError("short")

def cleanup() -> None:
    with contextlib.suppress(ValueError):  # silent: cleanup is best-effort at shutdown
        int("not-a-number")

def parse_optional() -> None:
    try:
        int("not-a-number")
    except ValueError:  # silent: absence is the documented optional result
        pass
""",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    _empty_baseline(baseline)

    result = _run(source, baseline)

    assert result.returncode == 0, result.stderr


def test_baseline_is_a_bidirectional_ratchet(tmp_path: Path) -> None:
    source = tmp_path / "ratchet.py"
    source.write_text(
        'def public() -> None:\n    raise ValueError("short")\n',
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"

    written = _run(source, baseline, write=True)
    assert written.returncode == 0, written.stderr
    assert _run(source, baseline).returncode == 0

    source.write_text(
        'def public() -> None:\n    raise ValueError("This actionable message now has enough words to guide users.")\n',
        encoding="utf-8",
    )
    stale = _run(source, baseline)
    assert stale.returncode == 1
    assert "Stale exception-hygiene baseline entries" in stale.stderr

    assert _run(source, baseline, write=True).returncode == 0
    assert _run(source, baseline).returncode == 0

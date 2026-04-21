"""Shared helpers for tests/cli/test_scaffold_*.py.

Each scaffold test runs in two phases:

1. **Scaffold in-process**: ``chirp.cli.main(["new", ...])`` writes template
   files into a tmp dir. For plain-v2 (no chirp-ui) we monkeypatch
   ``chirp.cli._new._has_chirpui`` to ``False`` before scaffolding.
2. **Evaluate out-of-process**: a fresh Python subprocess imports the
   generated ``app.py``, freezes it, and emits JSON on stdout. Running in
   a subprocess isolates us from state that ``App()`` registers at module
   scope (fragment target registry, routes, middleware chains) — which
   would otherwise contaminate subsequent parametrized runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCAFFOLD_MODES = ["minimal", "sse", "shell", "v2", "v2_plain"]


def _mode_args(mode: str) -> list[str]:
    if mode == "minimal":
        return ["--minimal"]
    if mode == "sse":
        return ["--sse"]
    if mode == "shell":
        return ["--shell"]
    return []  # v2 / v2_plain


def scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str) -> Path:
    """Write a scaffold project into ``tmp_path/project`` and return its path.

    ``mode="v2_plain"`` forces the non-chirpui variant by monkeypatching the
    feature detector (the dev env has chirp-ui installed, so the default v2
    branch would pick chirpui otherwise).
    """
    from chirp.cli import main

    if mode == "v2_plain":
        import chirp.cli._new as _new_mod

        monkeypatch.setattr(_new_mod, "_has_chirpui", lambda: False)

    monkeypatch.chdir(tmp_path)
    main(["new", "project", *_mode_args(mode)])
    return tmp_path / "project"


def run_in_scaffold(
    scaffold_dir: Path,
    code: str,
    *,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run ``code`` via ``python -c`` inside ``scaffold_dir``.

    CHIRP_SECRET_KEY is set so production-guards don't trip. Contract checks
    are skipped at freeze so the test can inspect issues without the process
    exiting on ERROR.
    """
    env = {
        **os.environ,
        "CHIRP_SECRET_KEY": "test-secret-key-for-contract-tests",
        "CHIRP_SKIP_CONTRACT_CHECKS": "1",
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=scaffold_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True, slots=True)
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any]


def run_and_parse(scaffold_dir: Path, code: str) -> SubprocessResult:
    """Run code in the scaffold and parse trailing-line JSON from stdout."""
    proc = run_in_scaffold(scaffold_dir, code)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        last = proc.stdout.strip().splitlines()[-1]
        try:
            payload = json.loads(last)
        except json.JSONDecodeError:
            payload = {}
    return SubprocessResult(proc.returncode, proc.stdout, proc.stderr, payload)

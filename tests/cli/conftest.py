"""Shared helpers for tests/cli/test_scaffold_*.py.

Each scaffold test runs in two phases:

1. **Scaffold in-process**: ``chirp.cli.main(["new", ...])`` writes template
   files into a tmp dir. Default modes are package-presence-independent;
   ``mode="v2_chirpui"`` passes ``--with-chirpui`` for the explicit
   compatibility scaffold.
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

SCAFFOLD_MODES = ["minimal", "sse", "shell", "v2", "v2_chirpui"]
DEPLOYABLE_SCAFFOLD_MODES = [*SCAFFOLD_MODES, "stream", "ai"]


def _mode_args(mode: str) -> list[str]:
    if mode == "minimal":
        return ["--minimal"]
    if mode == "sse":
        return ["--sse"]
    if mode == "shell":
        return ["--shell"]
    if mode == "stream":
        return ["--stream"]
    if mode == "ai":
        return ["--ai"]
    if mode == "v2_chirpui":
        return ["--with-chirpui"]
    return []


def scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str) -> Path:
    """Write a scaffold project into ``tmp_path/project`` and return its path.

    ``mode="v2"`` always emits the app-owned scaffold. ``mode="v2_chirpui"``
    explicitly requests the compatibility scaffold.
    """
    from chirp.cli import main

    monkeypatch.chdir(tmp_path)
    main(["new", "project", *_mode_args(mode)])
    return tmp_path / "project"


def run_in_scaffold(
    scaffold_dir: Path,
    code: str,
    *,
    timeout: float = 30.0,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``code`` via ``python -c`` inside ``scaffold_dir``.

    CHIRP_SECRET_KEY is set so production-guards don't trip. Contract checks
    are skipped at freeze so the test can inspect issues without the process
    exiting on ERROR. ``extra_env`` overlays additional env vars (e.g.
    ``CHIRP_ENV=production``) so a test can drive the generated app's own
    env-aware config.
    """
    env = {
        **os.environ,
        "CHIRP_SECRET_KEY": "test-secret-key-for-contract-tests",
        "CHIRP_SKIP_CONTRACT_CHECKS": "1",
    }
    if extra_env:
        env.update(extra_env)
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


def run_and_parse(
    scaffold_dir: Path, code: str, *, extra_env: dict[str, str] | None = None
) -> SubprocessResult:
    """Run code in the scaffold and parse trailing-line JSON from stdout."""
    proc = run_in_scaffold(scaffold_dir, code, extra_env=extra_env)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        last = proc.stdout.strip().splitlines()[-1]
        try:
            payload = json.loads(last)
        except json.JSONDecodeError:
            payload = {}
    return SubprocessResult(proc.returncode, proc.stdout, proc.stderr, payload)

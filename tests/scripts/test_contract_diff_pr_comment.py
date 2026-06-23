"""Tests for scripts/contract_diff_pr_comment.py (issue #344)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from chirp.contracts.diff import ContractDiff

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "contract_diff_pr_comment.py"
_spec = importlib.util.spec_from_file_location("contract_diff_pr_comment", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["contract_diff_pr_comment"] = _mod
_spec.loader.exec_module(_mod)
main = _mod.main


@pytest.mark.issue(344)
def test_fail_on_new_errors_exits_nonzero() -> None:
    added = (
        {
            "severity": "error",
            "category": "sse",
            "message": "no signal() binding",
            "template": "tasks.html",
            "route": None,
            "details": None,
        },
    )
    diff = ContractDiff(added=added, removed=())
    payload = {"diff": {"added": list(added), "removed": []}}

    with patch(
        "contract_diff_pr_comment.collect_diff_payload",
        return_value=(diff, payload),
    ):
        code = main(
            [
                "--app",
                "examples.chirpui.forum_shell.app:app",
                "--base",
                "origin/main",
                "--dry-run",
                "--fail-on-new-errors",
            ]
        )
    assert code == 1


@pytest.mark.issue(344)
def test_fail_on_new_errors_passes_when_clean() -> None:
    diff = ContractDiff(added=(), removed=())
    payload = {"diff": {"added": [], "removed": []}}

    with patch(
        "contract_diff_pr_comment.collect_diff_payload",
        return_value=(diff, payload),
    ):
        code = main(
            [
                "--app",
                "examples.chirpui.forum_shell.app:app",
                "--base",
                "origin/main",
                "--dry-run",
                "--fail-on-new-errors",
            ]
        )
    assert code == 0

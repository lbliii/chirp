"""Tests for scripts/contract_diff_pr_comment.py (issue #344)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from chirp.contracts.diff import ContractDiff

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "contract_diff_pr_comment.py"
_SPEC = importlib.util.spec_from_file_location("contract_diff_pr_comment", _SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["contract_diff_pr_comment"] = _MOD
_SPEC.loader.exec_module(_MOD)
main = _MOD.main


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

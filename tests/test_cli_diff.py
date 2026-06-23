"""Tests for chirp.cli._diff — ``chirp diff`` subcommand."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from chirp.cli._diff import run_diff
from chirp.contracts.surface_diff import check_at_git_ref, find_git_root
from chirp.contracts.diff import diff_contract_dicts


@pytest.mark.issue(344)
def test_find_git_root() -> None:
    root = find_git_root(Path(__file__).resolve())
    assert (root / ".git").exists()


@pytest.mark.issue(344)
def test_check_at_git_ref_matches_current_head() -> None:
    pytest.importorskip("chirp_ui")
    repo_root = find_git_root()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo_root,
        text=True,
    ).strip()
    payload = check_at_git_ref(
        "examples.chirpui.forum_shell.app:app",
        head,
        repo_root=repo_root,
    )
    assert "issues" in payload
    assert "routes_checked" in payload


@pytest.mark.issue(344)
def test_diff_self_has_no_changes(capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("chirp_ui")
    repo_root = find_git_root()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo_root,
        text=True,
    ).strip()
    baseline = check_at_git_ref(
        "examples.chirpui.forum_shell.app:app",
        head,
        repo_root=repo_root,
    )
    current = check_at_git_ref(
        "examples.chirpui.forum_shell.app:app",
        head,
        repo_root=repo_root,
    )
    diff = diff_contract_dicts(baseline, current)
    assert not diff.has_changes

    args = type(
        "Args",
        (),
        {
            "app": "examples.chirpui.forum_shell.app:app",
            "base": head,
            "json": False,
            "deploy": False,
            "warnings_as_errors": False,
            "include_info": False,
        },
    )()
    with patch("chirp.contracts.surface_diff.check_at_git_ref", return_value=baseline):
        run_diff(args)
    out = capsys.readouterr().out
    assert "no issue changes" in out


@pytest.mark.issue(344)
def test_diff_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("chirp_ui")
    repo_root = find_git_root()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo_root,
        text=True,
    ).strip()
    baseline = check_at_git_ref(
        "examples.chirpui.forum_shell.app:app",
        head,
        repo_root=repo_root,
    )

    args = type(
        "Args",
        (),
        {
            "app": "examples.chirpui.forum_shell.app:app",
            "base": head,
            "json": True,
            "deploy": False,
            "warnings_as_errors": False,
            "include_info": False,
        },
    )()
    with patch("chirp.contracts.surface_diff.check_at_git_ref", return_value=baseline):
        run_diff(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["base_ref"] == head
    assert not payload["diff"]["added"]
    assert not payload["diff"]["removed"]

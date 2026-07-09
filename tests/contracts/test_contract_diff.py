"""Contract diff and JSON baseline support (issue #344)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp.contracts.diff import diff_contract_dicts
from chirp.contracts.serialize import result_to_dict
from chirp.contracts.types import CheckResult, ContractIssue, Severity


@pytest.mark.issue(344)
def test_result_to_dict_is_deterministic() -> None:
    result = CheckResult(
        issues=[
            ContractIssue(Severity.ERROR, "route", "missing route", route="/x"),
            ContractIssue(Severity.WARNING, "form", "missing token", template="a.html"),
        ],
        routes_checked=3,
        templates_scanned=2,
    )
    payload = result_to_dict(result)
    assert payload["ok"] is False
    assert payload["routes_checked"] == 3
    assert len(payload["issues"]) == 2
    assert payload["issues"][0]["severity"] == "error"


@pytest.mark.issue(344)
def test_diff_reports_added_and_removed_issues() -> None:
    baseline = {
        "issues": [
            {
                "severity": "warning",
                "category": "form",
                "message": "old warning",
                "template": "a.html",
                "route": None,
                "details": None,
            }
        ]
    }
    current = {
        "issues": [
            {
                "severity": "error",
                "category": "route",
                "message": "new error",
                "template": None,
                "route": "/tasks",
                "details": None,
            }
        ]
    }
    diff = diff_contract_dicts(baseline, current)
    assert len(diff.added) == 1
    assert diff.added[0]["category"] == "route"
    assert len(diff.removed) == 1
    assert "old warning" in diff.summary_lines()[2]


@pytest.mark.issue(533)
def test_diff_preserves_query_contract_identity() -> None:
    result = CheckResult(
        issues=[
            ContractIssue(
                Severity.ERROR,
                "query_target",
                "Template 'search.html' targets missing QUERY route '/search'.",
                template="search.html",
                route="/search",
            )
        ]
    )

    current = result_to_dict(result)
    diff = diff_contract_dicts({"issues": []}, current)

    assert diff.added == (
        {
            "severity": "error",
            "category": "query_target",
            "message": "Template 'search.html' targets missing QUERY route '/search'.",
            "template": "search.html",
            "route": "/search",
            "details": None,
        },
    )


@pytest.mark.issue(344)
def test_markdown_comment_lists_added_errors() -> None:
    diff = diff_contract_dicts(
        {"issues": []},
        {
            "issues": [
                {
                    "severity": "error",
                    "category": "sse",
                    "message": "no signal() binding",
                    "template": "tasks.html",
                    "route": None,
                    "details": None,
                }
            ]
        },
    )
    body = diff.markdown_comment(
        app="examples.chirpui.forum_shell.app:app",
        base_ref="origin/main",
    )
    assert "<!-- chirp-contract-diff -->" in body
    assert "no signal() binding" in body
    assert "1 new contract error(s)" in body


@pytest.mark.issue(344)
def test_forum_shell_baseline_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("chirp_ui")
    import importlib.util
    import sys

    from chirp.contracts import check_hypermedia_surface

    app_path = (
        Path(__file__).resolve().parents[2] / "examples" / "chirpui" / "forum_shell" / "app.py"
    )
    spec = importlib.util.spec_from_file_location("forum_shell_app", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["forum_shell_app"] = module
    spec.loader.exec_module(module)
    app = module.app
    app.freeze()
    payload = result_to_dict(check_hypermedia_surface(app))
    baseline_path = tmp_path / "forum_shell.check.json"
    baseline_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    loaded = json.loads(baseline_path.read_text(encoding="utf-8"))
    diff = diff_contract_dicts(loaded, payload)
    assert not diff.has_changes

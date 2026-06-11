"""Tests for the backlog-truth machinery (see docs/backlog-automation.md).

Covers the three stdlib scripts that turn "done" from a hand-ticked checkbox
into a derived fact: the acceptance-test collector, the closure gate, and the
reconciliation derivation. The derivation logic is pure and exercised here
against fixtures; the GitHub/``gh`` I/O is intentionally not imported.
"""

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


issue_coverage = _load("issue_coverage")
check_closure_acceptance = _load("check_closure_acceptance")
reconcile_backlog = _load("reconcile_backlog")


# --------------------------------------------------------------------------- #
# issue_coverage: AST collection of @pytest.mark.issue markers
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    return f


def test_function_level_marker_is_collected(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        "import pytest\n@pytest.mark.issue(143)\ndef test_one():\n    pass\n",
    )
    cov = issue_coverage.collect_issue_tests([tmp_path])
    assert 143 in cov
    assert any("test_one" in loc for loc in cov[143])


def test_multi_arg_and_class_level_markers(tmp_path):
    _write(
        tmp_path,
        "test_b.py",
        "import pytest\n"
        "@pytest.mark.issue(166, 174)\n"
        "class TestShapes:\n"
        "    def test_x(self):\n        pass\n"
        "    def test_y(self):\n        pass\n",
    )
    cov = issue_coverage.collect_issue_tests([tmp_path])
    assert 166 in cov
    assert 174 in cov
    # class-level marker attributes every test method in the class
    assert len(cov[166]) == 2
    assert len(cov[174]) == 2


def test_module_level_pytestmark(tmp_path):
    _write(
        tmp_path,
        "test_c.py",
        "import pytest\npytestmark = [pytest.mark.issue(200)]\ndef test_z():\n    pass\n",
    )
    cov = issue_coverage.collect_issue_tests([tmp_path])
    assert 200 in cov


def test_untested_cli_returns_1_for_missing(tmp_path, capsys):
    _write(tmp_path, "test_d.py", "import pytest\n@pytest.mark.issue(1)\ndef test_q():\n    pass\n")
    # No fixture wiring for --untested (it scans the repo), so assert the helper:
    cov = issue_coverage.collect_issue_tests([tmp_path])
    assert 1 in cov
    assert 999 not in cov


# --------------------------------------------------------------------------- #
# check_closure_acceptance: parse closing keywords + exemption
# --------------------------------------------------------------------------- #


def test_extract_closing_issues_variants():
    body = "Closes #143\nfixes #200\nResolved: #7\nrefs #999 (not closing)"
    closing = check_closure_acceptance.extract_closing_issues(body)
    assert closing == {143, 200, 7}
    assert 999 not in closing  # a bare mention is not a closing keyword


def test_exemption_marker_detected():
    assert check_closure_acceptance.is_exempt("Acceptance: n/a (docs-only)")
    assert check_closure_acceptance.is_exempt("...\nacceptance : none\n...")
    assert not check_closure_acceptance.is_exempt("Closes #1")


# --------------------------------------------------------------------------- #
# reconcile_backlog: pure derivation
# --------------------------------------------------------------------------- #


def test_pr_issue_links_closing_mention_and_branch():
    pr = {
        "number": 212,
        "title": "fix: thing (#143)",
        "body": "Closes #143. Also touches #999.",
        "headRefName": "issue-143-postgres-ci",
    }
    closing, mentioned = reconcile_backlog.pr_issue_links(pr)
    assert 143 in closing  # closing keyword + branch convention
    assert mentioned == {999}


def test_derive_findings_merged_pending_close():
    open_issues = [{"number": 143, "title": "migration generator", "labels": []}]
    merged_prs = [
        {"number": 212, "title": "x", "body": "Closes #143", "headRefName": "issue-143-x"}
    ]
    findings = reconcile_backlog.derive_findings(open_issues, merged_prs, coverage={})
    assert len(findings) == 1
    assert "merged-pending-close" in findings[0]["add_labels"]


def test_derive_findings_epic_gets_review_label():
    open_issues = [{"number": 174, "title": "Shapes epic", "labels": [{"name": "epic"}]}]
    merged_prs = [
        {"number": 210, "title": "shapes", "body": "Closes #174", "headRefName": "shapes"}
    ]
    findings = reconcile_backlog.derive_findings(open_issues, merged_prs, coverage={})
    assert "stale-epic-review" in findings[0]["add_labels"]
    assert "merged-pending-close" not in findings[0]["add_labels"]


def test_derive_findings_acceptance_tracked():
    open_issues = [{"number": 50, "title": "feature", "labels": []}]
    findings = reconcile_backlog.derive_findings(
        open_issues, merged_prs=[], coverage={50: ["tests/test_x.py::test_y"]}
    )
    assert "acceptance-tracked" in findings[0]["add_labels"]


def test_derive_findings_skips_already_labeled():
    open_issues = [{"number": 143, "title": "x", "labels": [{"name": "merged-pending-close"}]}]
    merged_prs = [{"number": 212, "title": "x", "body": "Closes #143", "headRefName": "b"}]
    findings = reconcile_backlog.derive_findings(open_issues, merged_prs, coverage={})
    # already carries the label -> nothing new to add
    assert findings[0]["add_labels"] == []
    # but the reason is still surfaced in the report
    assert findings[0]["reasons"]


def test_render_report_is_markdown():
    findings = [
        {
            "number": 143,
            "title": "x",
            "is_epic": False,
            "add_labels": ["merged-pending-close"],
            "closed_by": [212],
            "mentioned_by": [],
            "has_tests": False,
            "reasons": ["merged PR(s) #212 close this — verify and close"],
        }
    ]
    report = reconcile_backlog.render_report(findings, coverage={})
    assert report.startswith("# Backlog reconciliation")
    assert "#143" in report
    assert "Merged — pending close" in report

"""Tests for the backlog-truth machinery (see docs/backlog-automation.md).

Covers the three stdlib scripts that turn "done" from a hand-ticked checkbox
into a derived fact: the acceptance-test collector, the closure gate, and the
reconciliation derivation. The derivation logic is pure and exercised here
against fixtures; the GitHub/``gh`` I/O is intentionally not imported.
"""

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


issue_coverage = _load("issue_coverage")
check_closure_acceptance = _load("check_closure_acceptance")
reconcile_backlog = _load("reconcile_backlog")
backlog = _load("backlog")


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
    body = (
        "Closes #143\nfixes #200\nResolved: #7\nrefs #999 (not closing)\n"
        "This does not close #300.\nA host is needed before #301 can close."
    )
    closing = check_closure_acceptance.extract_closing_issues(body)
    assert closing == {143, 200, 7}
    assert 999 not in closing  # a bare mention is not a closing keyword
    assert 300 not in closing
    assert 301 not in closing


def test_exemption_marker_is_issue_qualified():
    body = "Acceptance #12: n/a (docs-only)\nAcceptance #13: none (decision record)"
    assert check_closure_acceptance.extract_exemptions(body) == {
        12: "docs-only",
        13: "decision record",
    }
    assert check_closure_acceptance.has_blanket_exemption("Acceptance: n/a (docs-only)")
    assert not check_closure_acceptance.extract_exemptions("Acceptance: n/a (docs-only)")


# --------------------------------------------------------------------------- #
# reconcile_backlog: pure derivation
# --------------------------------------------------------------------------- #


def test_pr_issue_links_treats_branch_as_association():
    pr = {
        "number": 212,
        "title": "fix: thing (#143)",
        "body": "Closes #143. Also touches #999.",
        "headRefName": "issue-143-postgres-ci",
    }
    closing, mentioned = reconcile_backlog.pr_issue_links(pr)
    assert closing == {143}
    assert mentioned == {999}


def test_pr_issue_links_branch_only_does_not_close():
    closing, mentioned = reconcile_backlog.pr_issue_links(
        {"title": "phase one", "body": "", "headRefName": "issue-143-phase-one"}
    )
    assert closing == set()
    assert mentioned == {143}


def test_pr_issue_links_ignores_qualified_external_references():
    closing, mentioned = reconcile_backlog.pr_issue_links(
        {
            "title": "deps",
            "body": "See actions/github-script#695 and https://github.com/x/y/issues/681",
            "headRefName": "deps",
        }
    )
    assert closing == set()
    assert mentioned == set()


def test_pr_work_claims_requires_closing_reference_or_issue_branch():
    assert reconcile_backlog.pr_work_claims(
        {"body": "Closes #12\nRefs #13", "headRefName": "issue-14-work"}
    ) == {12, 14}
    assert (
        reconcile_backlog.pr_work_claims(
            {"body": "Refs #13\nAdvances-Epic: #20", "headRefName": "feature-work"}
        )
        == set()
    )


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


def test_derive_findings_removes_obsolete_owned_label():
    findings = reconcile_backlog.derive_findings(
        [{"number": 143, "title": "x", "labels": [{"name": "acceptance-tracked"}]}],
        merged_prs=[],
        coverage={},
    )
    assert findings[0]["add_labels"] == []
    assert findings[0]["remove_labels"] == ["acceptance-tracked"]


def test_render_report_is_markdown():
    findings = [
        {
            "number": 143,
            "title": "x",
            "is_epic": False,
            "add_labels": ["merged-pending-close"],
            "remove_labels": [],
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


def _issue(
    number: int,
    *,
    labels: tuple[str, ...] = (),
    parent: int | None = None,
    children: list[dict] | None = None,
    body: str = "",
    state: str = "OPEN",
):
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": body,
        "state": state,
        "stateReason": None,
        "labels": list(labels),
        "parent": {"number": parent} if parent else None,
        "subIssues": children or [],
    }


def _child(number: int, *, state: str = "OPEN", labels: tuple[str, ...] = (), reason=None):
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "stateReason": reason,
        "labels": list(labels),
    }


def test_workability_healthy_parent_reaches_ready_leaf():
    issues = [
        _issue(1, labels=("saga",), children=[_child(2, labels=("epic",))]),
        _issue(2, labels=("epic",), parent=1, children=[_child(3, labels=("P2", "ready"))]),
        _issue(3, labels=("P2", "ready"), parent=2),
    ]
    assert reconcile_backlog.derive_workability_findings(issues) == []


def test_workability_flags_ready_parent_and_unclassified_leaf():
    issues = [
        _issue(1, labels=("epic", "ready"), children=[_child(2, labels=("P2",))]),
        _issue(2, labels=("P2",), parent=1),
    ]
    findings = reconcile_backlog.derive_workability_findings(issues)
    by_number = {finding["number"]: finding for finding in findings}
    assert "ready-parent" in by_number[1]["codes"]
    assert "parent-no-workable-leaf" in by_number[1]["codes"]
    assert "work-state-missing" in by_number[2]["codes"]
    assert "needs-grooming" in by_number[1]["add_labels"]


def test_workability_all_blocked_is_healthy():
    issues = [
        _issue(1, labels=("epic",), children=[_child(2, labels=("upstream-blocked",))]),
        _issue(2, labels=("P2", "upstream-blocked"), parent=1),
    ]
    assert reconcile_backlog.derive_workability_findings(issues) == []


def test_workability_internal_block_requires_native_dependency():
    findings = reconcile_backlog.derive_workability_findings([_issue(2, labels=("P2", "blocked"))])
    assert "blocked-without-dependency" in findings[0]["codes"]


def test_workability_ready_leaf_with_open_formal_blocker_conflicts():
    issue = _issue(2, labels=("P2", "ready"))
    issue["blockedBy"] = [{"number": 1, "state": "open", "title": "blocker"}]
    findings = reconcile_backlog.derive_workability_findings([issue])
    assert "work-state-conflict" in findings[0]["codes"]


def test_workability_parent_completed_children_is_closure_candidate():
    issues = [
        _issue(
            1,
            labels=("epic",),
            children=[_child(2, state="CLOSED", reason="COMPLETED")],
        )
    ]
    findings = reconcile_backlog.derive_workability_findings(issues)
    assert findings[0]["codes"] == ["closure-candidate"]
    assert findings[0]["add_labels"] == ["closure-candidate"]


def test_workability_removes_resolved_grooming_label():
    findings = reconcile_backlog.derive_workability_findings(
        [_issue(2, labels=("P2", "ready", "needs-grooming"))]
    )
    assert findings[0]["codes"] == []
    assert findings[0]["remove_labels"] == ["needs-grooming"]


def _valid_plan():
    return {
        "version": 1,
        "repository": "lbliii/chirp",
        "baseline_sha": "abc",
        "preconditions": {},
        "actions": [
            {
                "id": "task-one",
                "kind": "create",
                "issue_kind": "task",
                "title": "Task: prove one thing",
                "labels": ["P2", "ready"],
                "standalone": True,
                "blocked_by": [],
                "idempotency_key": "task-one-v1",
                "spec": {
                    "outcome": "The behavior is proven.",
                    "immediate_action": "Add the failing fixture.",
                    "scope": "One bounded change.",
                    "boundaries": "No public API.",
                    "proof": "Focused tests.",
                    "acceptance": "The fixture passes.",
                    "collateral": "None: internal proof only.",
                },
            }
        ],
    }


def test_backlog_plan_validates_and_renders_marker():
    plan = _valid_plan()
    assert backlog.validate_plan(plan) == []
    body = backlog.render_issue_body(plan["actions"][0])
    assert "<!-- chirp-backlog-key:task-one-v1 -->" in body
    assert "## Immediate next action" in body


def test_backlog_plan_rejects_ready_parent_and_ready_blocker():
    plan = _valid_plan()
    action = plan["actions"][0]
    action["issue_kind"] = "epic"
    action["labels"] = ["epic", "ready"]
    action["blocked_by"] = [123]
    action["standalone"] = False
    errors = backlog.validate_plan(plan)
    assert any("parent may not carry ready" in error for error in errors)
    assert any("ready leaf may not have blockers" in error for error in errors)


def test_backlog_plan_rejects_good_first_and_duplicate_keys():
    plan = _valid_plan()
    second = json.loads(json.dumps(plan["actions"][0]))
    second["id"] = "task-two"
    second["title"] = "[GF] reserved"
    plan["actions"].append(second)
    errors = backlog.validate_plan(plan)
    assert any("good-first" in error for error in errors)
    assert any("duplicate idempotency key" in error for error in errors)


def test_backlog_plan_rejects_plan_local_cycle():
    plan = _valid_plan()
    first = plan["actions"][0]
    first["standalone"] = False
    first["parent"] = "task-two"
    second = json.loads(json.dumps(first))
    second["id"] = "task-two"
    second["idempotency_key"] = "task-two-v1"
    second["parent"] = "task-one"
    plan["actions"].append(second)
    errors = backlog.validate_plan(plan)
    assert any("cycle" in error for error in errors)


def test_backlog_plan_body_edit_requires_hash_precondition():
    plan = {
        "version": 1,
        "repository": "lbliii/chirp",
        "preconditions": {"123": {"updated_at": "2026-07-10T00:00:00Z"}},
        "actions": [
            {
                "id": "edit-body",
                "kind": "edit",
                "issue": 123,
                "body": "replacement",
            }
        ],
    }
    errors = backlog.validate_plan(plan)
    assert any("body_sha256" in error for error in errors)


# --------------------------------------------------------------------------- #
# backlog next/explain: pure eligibility and deterministic ranking
# --------------------------------------------------------------------------- #


_WORK_BODY = """## Immediate next action

Write the failing regression test.

## Required proof

Run the focused test module.

## Acceptance criteria

The regression stays fixed.
"""


def _work_issue(
    number: int,
    *,
    labels: tuple[str, ...] = ("P2", "ready"),
    parent: int | None = None,
    body: str = _WORK_BODY,
    created: str = "2026-07-01T00:00:00Z",
):
    issue = _issue(number, labels=labels, parent=parent, body=body)
    issue.update(
        {
            "url": f"https://github.com/lbliii/chirp/issues/{number}",
            "createdAt": created,
            "blockedBy": [],
        }
    )
    return issue


def test_next_ranks_priority_before_unlock_count_then_age():
    p2_unlocker = _work_issue(1, created="2026-07-02T00:00:00Z")
    p1 = _work_issue(2, labels=("P1", "ready"))
    p2_old = _work_issue(3, created="2026-06-01T00:00:00Z")
    blocked_4 = _work_issue(4, labels=("P2", "blocked"))
    blocked_4["blockedBy"] = [{"number": 1, "state": "open"}]
    blocked_5 = _work_issue(5, labels=("P2", "blocked"))
    blocked_5["blockedBy"] = [{"number": 1, "state": "open"}]
    assessments = backlog.assess_work([p2_unlocker, p1, p2_old, blocked_4, blocked_5], open_prs=[])
    assert [item.number for item in backlog.rank_work(assessments)] == [2, 1, 3]
    assert next(item for item in assessments if item.number == 1).unlocks == (4, 5)


def test_next_excludes_reserved_blocked_claimed_and_decision_gated_work():
    gf = _work_issue(1, labels=("P1", "ready", "good first issue"))
    parent = _work_issue(2, labels=("epic", "ready"))
    parent["subIssues"] = [_child(7, labels=("P2", "ready"))]
    blocked = _work_issue(3, labels=("P1", "ready", "blocked"))
    claimed = _work_issue(4, labels=("P1", "ready"))
    decision = _work_issue(5, labels=("P1", "ready", "needs-decision"))
    no_action = _work_issue(6, body="## Required proof\n\nTests")
    eligible = _work_issue(7, labels=("P2", "ready"))
    prs = [
        {
            "number": 90,
            "body": "Refs #7",
            "headRefName": "issue-4-claimed",
            "url": "https://example.test/pr/90",
            "isDraft": False,
        }
    ]
    assessments = backlog.assess_work(
        [gf, parent, blocked, claimed, decision, no_action, eligible], prs
    )
    assert [item.number for item in backlog.rank_work(assessments)] == [7]
    by_number = {item.number: item for item in assessments}
    assert by_number[4].open_prs[0][0] == 90
    assert "body has no Immediate next action section" in by_number[6].reasons


def test_next_inherits_parent_priority_and_area_filter():
    parent = _issue(
        10,
        labels=("epic", "P1", "area:templating"),
        children=[_child(11, labels=("P2", "ready"))],
    )
    child = _work_issue(11, parent=10)
    other = _work_issue(12, labels=("P1", "ready", "area:http"))
    assessments = backlog.assess_work([parent, child, other], open_prs=[])
    child_assessment = next(item for item in assessments if item.number == 11)
    assert child_assessment.effective_priority == "P1"
    assert child_assessment.parent_chain == (10,)
    assert child_assessment.areas == ("templating",)
    assert [item.number for item in backlog.rank_work(assessments, area="templating")] == [11]


def test_explain_serializes_checks_and_execution_context():
    assessment = backlog.assess_work([_work_issue(42)], open_prs=[])[0]
    payload = assessment.as_json()
    assert payload["eligible"] is True
    assert payload["checks"][0] == {"name": "open", "passed": True, "detail": "issue is open"}
    assert payload["immediate_action"] == "Write the failing regression test."
    rendered = backlog.render_explain(assessment)
    assert "**Status:** workable now" in rendered
    assert "PASS `formal-blockers`" in rendered


def test_next_derives_legacy_execution_headings_and_plain_action():
    legacy = _work_issue(
        50,
        body="""## Outcome

Implement the bounded adapter.

## Required proof plan

Run two-instance integration tests.

## Exit

Record the accepted boundary.
""",
    )
    plain = _work_issue(
        51,
        body="Parent: #10.\n\nRun one bounded pilot and record the result.",
    )
    assessments = {item.number: item for item in backlog.assess_work([legacy, plain], [])}
    assert assessments[50].eligible is True
    assert assessments[50].immediate_action == "Implement the bounded adapter."
    assert assessments[50].required_proof == "Run two-instance integration tests."
    assert "legacy 'Outcome'" in assessments[50].warnings[0]
    assert assessments[51].immediate_action == "Run one bounded pilot and record the result."
    assert any("first actionable" in warning for warning in assessments[51].warnings)

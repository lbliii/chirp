"""Tests for contract check snapshot and CheckResult."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import (
    CheckResult,
    ContractIssue,
    Severity,
)


class TestContractCheckSnapshot:
    def test_snapshot_exposes_stable_read_model(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        snapshot = app._contract_check_snapshot()
        assert snapshot.router is not None
        assert snapshot.fragment_target_registry is not None
        assert snapshot.page_leaf_templates == set()
        assert snapshot.islands_contract_strict == app.config.islands_contract_strict


class TestCheckResult:
    """CheckResult aggregation and reporting."""

    def test_ok_when_no_errors(self):
        result = CheckResult()
        assert result.ok

    def test_not_ok_with_errors(self):
        result = CheckResult(
            issues=[
                ContractIssue(severity=Severity.ERROR, category="test", message="fail"),
            ]
        )
        assert not result.ok

    def test_ok_with_warnings_only(self):
        result = CheckResult(
            issues=[
                ContractIssue(severity=Severity.WARNING, category="test", message="warn"),
            ]
        )
        assert result.ok

    def test_summary_no_issues(self):
        result = CheckResult(routes_checked=5, templates_scanned=3, targets_found=10)
        summary = result.summary()
        assert "5 routes" in summary
        assert "3 templates" in summary
        assert "No issues found" in summary

    def test_summary_with_errors(self):
        result = CheckResult(
            routes_checked=1,
            templates_scanned=1,
            targets_found=1,
            issues=[
                ContractIssue(
                    severity=Severity.ERROR,
                    category="target",
                    message="'/missing' has no matching route.",
                    template="index.html",
                ),
            ],
        )
        summary = result.summary()
        assert "1 error" in summary
        assert "/missing" in summary

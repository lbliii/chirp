"""Tests for app.override_contract_severity()."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.app.state import ContractCheckSnapshot
from chirp.contracts import CheckResult, ContractIssue, Severity, check_hypermedia_surface


class TestSeverityOverrides:
    """Severity overrides change issue severity as a post-processing step."""

    def test_override_info_to_warning(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def info_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="my_info",
                    message="Low priority note.",
                )
            )

        app.register_contract_check(info_check)
        app.override_contract_severity("my_info", Severity.WARNING)
        result = check_hypermedia_surface(app)

        my_issues = [i for i in result.issues if i.category == "my_info"]
        assert len(my_issues) == 1
        assert my_issues[0].severity == Severity.WARNING

    def test_override_error_to_warning(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def error_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="strict_rule",
                    message="Was an error.",
                )
            )

        app.register_contract_check(error_check)
        app.override_contract_severity("strict_rule", Severity.WARNING)
        result = check_hypermedia_surface(app)

        my_issues = [i for i in result.issues if i.category == "strict_rule"]
        assert len(my_issues) == 1
        assert my_issues[0].severity == Severity.WARNING
        # Downgraded from ERROR, so result.ok should be True (no errors)
        strict_errors = [
            i for i in result.issues if i.category == "strict_rule" and i.severity == Severity.ERROR
        ]
        assert len(strict_errors) == 0

    def test_override_warning_to_error(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def warn_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="promoted",
                    message="Was a warning.",
                )
            )

        app.register_contract_check(warn_check)
        app.override_contract_severity("promoted", Severity.ERROR)
        result = check_hypermedia_surface(app)

        my_issues = [i for i in result.issues if i.category == "promoted"]
        assert len(my_issues) == 1
        assert my_issues[0].severity == Severity.ERROR

    def test_override_unknown_category_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app.override_contract_severity("nonexistent_category", Severity.ERROR)
        # Should not raise
        result = check_hypermedia_surface(app)
        assert result is not None

    def test_override_preserves_message_and_metadata(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def detailed_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="detailed",
                    message="Check this out.",
                    template="page.html",
                    route="/",
                    details="Extra details here.",
                )
            )

        app.register_contract_check(detailed_check)
        app.override_contract_severity("detailed", Severity.ERROR)
        result = check_hypermedia_surface(app)

        my_issues = [i for i in result.issues if i.category == "detailed"]
        assert len(my_issues) == 1
        issue = my_issues[0]
        assert issue.severity == Severity.ERROR
        assert issue.message == "Check this out."
        assert issue.template == "page.html"
        assert issue.route == "/"
        assert issue.details == "Extra details here."

    def test_override_only_affects_matching_category(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def multi_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(severity=Severity.INFO, category="cat_a", message="A")
            )
            result.issues.append(
                ContractIssue(severity=Severity.INFO, category="cat_b", message="B")
            )

        app.register_contract_check(multi_check)
        app.override_contract_severity("cat_a", Severity.ERROR)
        result = check_hypermedia_surface(app)

        a_issues = [i for i in result.issues if i.category == "cat_a"]
        b_issues = [i for i in result.issues if i.category == "cat_b"]
        assert a_issues[0].severity == Severity.ERROR
        assert b_issues[0].severity == Severity.INFO

    def test_override_after_freeze_raises(self, tmp_path: Path) -> None:
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        with pytest.raises(RuntimeError, match="Cannot modify"):
            app.override_contract_severity("dead", Severity.ERROR)

    def test_override_applies_to_builtin_categories(self, tmp_path: Path) -> None:
        """Override applies to built-in rule categories like 'dead'."""
        # Create an unreferenced template to trigger a 'dead' issue
        (tmp_path / "page.html").write_text("<div>used</div>")
        (tmp_path / "orphan.html").write_text("<div>orphan</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/", template="page.html")
        def index():
            return {}

        app.override_contract_severity("dead", Severity.ERROR)
        result = check_hypermedia_surface(app)

        dead_issues = [i for i in result.issues if i.category == "dead"]
        for issue in dead_issues:
            assert issue.severity == Severity.ERROR

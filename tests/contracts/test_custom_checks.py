"""Tests for the custom contract check plugin system."""

import pytest

from chirp import App, ContractCheck
from chirp.app.state import ContractCheckSnapshot
from chirp.config import AppConfig
from chirp.contracts import CheckResult, ContractIssue, Severity, check_hypermedia_surface


class TestRegistration:
    """Registration-time behavior for custom contract checks."""

    def test_register_function_check(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        def my_check(snapshot, result):
            pass

        app.register_contract_check(my_check)
        assert my_check in app._mutable_state.contract_checks

    def test_register_callable_class(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        class MyCheck:
            def __call__(self, snapshot, result):
                pass

        check = MyCheck()
        app.register_contract_check(check)
        assert check in app._mutable_state.contract_checks

    def test_register_non_callable_raises(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))
        with pytest.raises(TypeError, match="callable"):
            app.register_contract_check("not a callable")  # type: ignore[arg-type]

    def test_register_after_freeze_raises(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        with pytest.raises(RuntimeError, match="Cannot modify"):
            app.register_contract_check(lambda s, r: None)


class TestExecution:
    """Custom checks run during app.check() and produce correct results."""

    def test_custom_check_appends_issues(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def my_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            result.issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="my_plugin",
                    message="Something to watch out for.",
                )
            )

        app.register_contract_check(my_check)
        result = check_hypermedia_surface(app)
        plugin_issues = [i for i in result.issues if i.category == "my_plugin"]
        assert len(plugin_issues) == 1
        assert plugin_issues[0].severity == Severity.WARNING

    def test_custom_check_receives_template_sources(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        received_sources = {}

        def source_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            received_sources.update(snapshot.template_sources)

        app.register_contract_check(source_check)
        check_hypermedia_surface(app)
        assert "page.html" in received_sources
        assert "hello" in received_sources["page.html"]

    def test_custom_check_receives_extras(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app.set_contract_check_data("my_registry", {"components": ["card", "modal"]})

        received_extras = {}

        def extras_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            received_extras.update(snapshot.extras)

        app.register_contract_check(extras_check)
        check_hypermedia_surface(app)
        assert received_extras["my_registry"] == {"components": ["card", "modal"]}

    def test_custom_check_exception_isolated(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        def bad_check(snapshot, result):
            raise ValueError("plugin crashed")

        def good_check(snapshot, result):
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="good_plugin",
                    message="I ran fine.",
                )
            )

        app.register_contract_check(bad_check)
        app.register_contract_check(good_check)
        result = check_hypermedia_surface(app)

        # bad_check's exception became an ERROR issue
        error_issues = [i for i in result.issues if i.category == "plugin_check_error"]
        assert len(error_issues) == 1
        assert "bad_check" in error_issues[0].message
        assert "ValueError" in error_issues[0].message
        assert "plugin crashed" not in error_issues[0].message
        assert "Repair surface: custom check 'bad_check'" in (error_issues[0].details or "")

        # good_check still ran
        good_issues = [i for i in result.issues if i.category == "good_plugin"]
        assert len(good_issues) == 1

    def test_no_custom_checks_unchanged(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        result = check_hypermedia_surface(app)
        # No plugin_check_error issues should exist
        plugin_issues = [i for i in result.issues if i.category == "plugin_check_error"]
        assert len(plugin_issues) == 0

    def test_checks_run_in_registration_order(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        order: list[str] = []

        def first(snapshot, result):
            order.append("first")

        def second(snapshot, result):
            order.append("second")

        def third(snapshot, result):
            order.append("third")

        app.register_contract_check(first)
        app.register_contract_check(second)
        app.register_contract_check(third)
        check_hypermedia_surface(app)
        assert order == ["first", "second", "third"]


class TestSetContractCheckData:
    """Tests for app.set_contract_check_data()."""

    def test_set_data_before_freeze(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))
        app.set_contract_check_data("key", "value")
        assert app._mutable_state.contract_check_data["key"] == "value"

    def test_set_data_after_freeze_raises(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        with pytest.raises(RuntimeError, match="Cannot modify"):
            app.set_contract_check_data("key", "value")

    def test_extras_empty_by_default(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._ensure_frozen()
        snapshot = app._contract_check_snapshot()
        assert snapshot.extras == {}


class TestContractCheckProtocol:
    """ContractCheck Protocol works for both function and class forms."""

    def test_function_satisfies_protocol(self):
        def my_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            pass

        check: ContractCheck = my_check  # type-check assignment
        assert callable(check)

    def test_class_satisfies_protocol(self):
        class MyCheck:
            def __call__(self, snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
                pass

        check: ContractCheck = MyCheck()  # type-check assignment
        assert callable(check)

    def test_protocol_check_runs_with_name(self, tmp_path):
        (tmp_path / "page.html").write_text("<div>hello</div>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        class NamedCheck:
            def __call__(self, snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
                result.issues.append(
                    ContractIssue(
                        severity=Severity.INFO,
                        category="named_check",
                        message="Class-based check ran.",
                    )
                )

        app.register_contract_check(NamedCheck())
        result = check_hypermedia_surface(app)
        named_issues = [i for i in result.issues if i.category == "named_check"]
        assert len(named_issues) == 1

    def test_protocol_importable_from_chirp(self):
        from chirp import ContractCheck as C

        assert C is not None

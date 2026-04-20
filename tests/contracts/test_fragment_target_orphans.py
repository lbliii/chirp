"""Tests for the fragment_target_orphan contract check."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.templating.fragment_target_registry import (
    PageShellContract,
    PageShellTarget,
)
from tests.helpers.contract_fixtures import write_layout_page


def _page_app(tmp_path, page_body: str = "{% block foo %}hi{% endblock %}") -> App:
    write_layout_page(
        tmp_path,
        "<html><body>{% block content %}{% endblock %}</body></html>",
        f'{{% extends "_layout.html" %}}{{% block content %}}{page_body}{{% endblock %}}',
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        return "ok"

    app._mutable_state.page_leaf_templates.add("page.html")
    app._mutable_state.page_templates.add("page.html")
    return app


def _orphans(result) -> list:
    return [i for i in result.issues if i.category == "fragment_target_orphan"]


class TestRequiredTargetOrphans:
    def test_required_target_missing_block_is_error(self, tmp_path):
        app = _page_app(tmp_path)
        app._mutable_state.fragment_target_registry.register(
            "page-root", fragment_block="never_defined", required=True
        )

        result = check_hypermedia_surface(app)
        errors = _orphans(result)
        assert len(errors) == 1
        assert errors[0].severity.name == "ERROR"
        assert "#page-root" in errors[0].message
        assert "never_defined" in errors[0].message

    def test_contract_required_target_missing_block_is_error(self, tmp_path):
        app = _page_app(tmp_path)
        contract = PageShellContract(
            name="myshell",
            targets=(
                PageShellTarget(target_id="main", fragment_block="absent_block", required=True),
            ),
        )
        app._mutable_state.fragment_target_registry.register_contract(contract)

        result = check_hypermedia_surface(app)
        errors = _orphans(result)
        assert len(errors) == 1
        assert "myshell" in errors[0].message
        assert "absent_block" in errors[0].message


class TestOptionalTargetOrphans:
    def test_optional_target_missing_block_is_warning(self, tmp_path):
        app = _page_app(tmp_path)
        app._mutable_state.fragment_target_registry.register(
            "sidebar", fragment_block="nope", required=False
        )

        result = check_hypermedia_surface(app)
        orphans = _orphans(result)
        assert len(orphans) == 1
        assert orphans[0].severity.name == "WARNING"
        assert "#sidebar" in orphans[0].message


class TestNoOrphanWhenBlockExists:
    def test_registered_target_matching_defined_block_is_clean(self, tmp_path):
        app = _page_app(tmp_path, page_body="{% block foo %}hi{% endblock %}")
        app._mutable_state.fragment_target_registry.register(
            "page-root", fragment_block="foo", required=True
        )

        result = check_hypermedia_surface(app)
        assert _orphans(result) == []

    def test_empty_registry_produces_no_issues(self, tmp_path):
        app = _page_app(tmp_path)

        result = check_hypermedia_surface(app)
        assert _orphans(result) == []


class TestSeverityOverride:
    def test_override_demotes_required_orphan_to_warning(self, tmp_path):
        from chirp.contracts import Severity

        app = _page_app(tmp_path)
        app._mutable_state.fragment_target_registry.register(
            "page-root", fragment_block="never_defined", required=True
        )
        app.override_contract_severity("fragment_target_orphan", Severity.WARNING)

        result = check_hypermedia_surface(app)
        orphans = _orphans(result)
        assert len(orphans) == 1
        assert orphans[0].severity == Severity.WARNING

"""Tests for page shell contract validation (ChirpUI)."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.ext.chirp_ui import CHIRPUI_PAGE_SHELL_CONTRACT, use_chirp_ui
from tests.helpers.contract_fixtures import write_layout_page


class TestPageShellContractValidation:
    def test_use_chirp_ui_registers_page_shell_contract(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))
        use_chirp_ui(app)

        registry = app._mutable_state.fragment_target_registry
        assert registry.registered_contracts == (CHIRPUI_PAGE_SHELL_CONTRACT,)
        assert registry.required_fragment_blocks == frozenset(
            {"page_root", "page_root_inner", "page_content"}
        )

    def test_checker_reports_missing_required_page_shell_blocks(self, tmp_path):
        write_layout_page(
            tmp_path,
            '{# target: body #}<main id="main">{% block content %}{% endblock %}</main>',
            '{% extends "_layout.html" %}{% block content %}<p>hello</p>{% endblock %}',
        )

        app = App(AppConfig(template_dir=str(tmp_path)))
        use_chirp_ui(app)

        @app.route("/")
        def index():
            return "ok"

        app._mutable_state.page_leaf_templates.add("page.html")
        app._mutable_state.page_templates.add("page.html")

        result = check_hypermedia_surface(app)
        page_shell_errors = [issue for issue in result.errors if issue.category == "page_shell"]
        assert len(page_shell_errors) == 1
        assert "page_root" in page_shell_errors[0].message
        assert "page_root_inner" in page_shell_errors[0].message
        assert "page_content" in page_shell_errors[0].message

    def test_checker_accepts_page_shell_templates_with_required_blocks(self, tmp_path):
        write_layout_page(
            tmp_path,
            '{# target: body #}<main id="main">{% block content %}{% endblock %}</main>',
            '{% extends "_page_layout.html" %}{% block page_content %}<p>hello</p>{% endblock %}',
            extra={
                "_page_layout.html": (
                    '{% extends "_layout.html" %}'
                    "{% block content %}"
                    "{% block page_root %}"
                    '<div id="page-root">'
                    "{% block page_root_inner %}"
                    '<div id="page-content-inner">{% block page_content %}{% endblock %}</div>'
                    "{% endblock %}"
                    "</div>"
                    "{% endblock %}"
                    "{% endblock %}"
                ),
            },
        )

        app = App(AppConfig(template_dir=str(tmp_path)))
        use_chirp_ui(app)

        @app.route("/")
        def index():
            return "ok"

        app._mutable_state.page_leaf_templates.add("page.html")
        app._mutable_state.page_templates.add("page.html")

        result = check_hypermedia_surface(app)
        page_shell_errors = [issue for issue in result.errors if issue.category == "page_shell"]
        assert page_shell_errors == []

"""Tests for form action → route contract matching.

Covers check_form_action_contracts: warns when POST forms target
routes without FormContract declarations.
"""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts.declarations import FormContract, contract
from chirp.contracts.rules_form_routes import check_form_action_contracts
from chirp.http.request import Request


class TestFormActionContracts:
    """Form POST targets should have FormContract for validation."""

    def test_form_with_contract_passes(self, tmp_path):
        (tmp_path / "login.html").write_text(
            '<form action="/login" method="post"><input name="username"><button>Go</button></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        from dataclasses import dataclass

        @dataclass
        class LoginForm:
            username: str

        @app.route("/login", methods=["GET", "POST"])
        @contract(form=FormContract(LoginForm, "login.html", "form"))
        async def login(request: Request):
            return "ok"

        app._ensure_frozen()
        sources = {"login.html": (tmp_path / "login.html").read_text()}
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 0

    def test_form_without_contract_reports_info(self, tmp_path):
        (tmp_path / "login.html").write_text(
            '<form action="/login" method="post"><input name="username"><button>Go</button></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/login", methods=["GET", "POST"])
        async def login(request: Request):
            return "ok"

        app._ensure_frozen()
        sources = {"login.html": (tmp_path / "login.html").read_text()}
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 1
        assert issues[0].severity.value == "info"
        assert issues[0].category == "form_contract"
        assert "/login" in issues[0].message

    def test_get_form_not_checked(self, tmp_path):
        """GET forms don't need FormContract."""
        (tmp_path / "search.html").write_text(
            '<form action="/search"><input name="q"><button>Search</button></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/search")
        async def search(request: Request):
            return "ok"

        app._ensure_frozen()
        sources = {"search.html": (tmp_path / "search.html").read_text()}
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 0

    def test_dynamic_action_skipped(self, tmp_path):
        """Forms with Kida expressions in action are skipped."""
        (tmp_path / "edit.html").write_text(
            '<form action="{{ edit_url }}" method="post"><button>Save</button></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/edit/{id}", methods=["POST"])
        async def edit(request: Request):
            return "ok"

        app._ensure_frozen()
        sources = {"edit.html": (tmp_path / "edit.html").read_text()}
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 0

    def test_no_post_routes_no_issues(self, tmp_path):
        (tmp_path / "page.html").write_text("<p>No forms</p>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/page")
        async def page():
            return "ok"

        app._ensure_frozen()
        sources = {"page.html": (tmp_path / "page.html").read_text()}
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 0

    def test_chirp_templates_skipped(self, tmp_path):
        """Internal chirp/ and chirpui/ templates are not checked."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/internal", methods=["POST"])
        async def internal():
            return "ok"

        app._ensure_frozen()
        sources = {
            "chirp/debug.html": '<form action="/internal" method="post"><button>X</button></form>',
        }
        issues = check_form_action_contracts(sources, app._router)
        assert len(issues) == 0

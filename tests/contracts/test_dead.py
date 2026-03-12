"""Tests for dead template detection in check_hypermedia_surface."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import (
    CheckResult,
    ContractIssue,
    FragmentContract,
    Severity,
    check_hypermedia_surface,
    contract,
)


def _user_dead(result: CheckResult) -> list[ContractIssue]:
    """Filter dead-template issues to only user templates (not built-in)."""

    def is_builtin(tmpl: str | None) -> bool:
        if not tmpl:
            return True
        return tmpl.startswith(("chirp/", "chirpui", "themes/"))

    return [i for i in result.issues if i.category == "dead" and not is_builtin(i.template)]


class TestDeadTemplateDetection:
    """Integration tests for dead template detection in check_hypermedia_surface."""

    def test_unreferenced_template_reported(self, tmp_path):
        """An unused template should be reported as dead."""
        (tmp_path / "index.html").write_text("{% block content %}<h1>Home</h1>{% endblock %}")
        (tmp_path / "unused.html").write_text("<h1>Old page</h1>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 1
        assert "unused.html" in dead[0].message
        assert dead[0].severity == Severity.INFO

    def test_included_template_not_dead(self, tmp_path):
        """A template referenced via include should not be reported."""
        (tmp_path / "index.html").write_text(
            '{% block content %}{% include "nav.html" %}{% endblock %}'
        )
        (tmp_path / "nav.html").write_text("<nav>links</nav>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_extended_template_not_dead(self, tmp_path):
        """A template referenced via extends should not be reported."""
        (tmp_path / "base.html").write_text("{% block content %}{% endblock %}")
        (tmp_path / "page.html").write_text(
            '{% extends "base.html" %}{% block content %}hi{% endblock %}'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("page.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_partial_excluded_by_convention(self, tmp_path):
        """Templates with _ prefix are partials and should be excluded."""
        (tmp_path / "index.html").write_text("{% block content %}<h1>Home</h1>{% endblock %}")
        (tmp_path / "_partial.html").write_text("<p>partial</p>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_fragment_contract_template_not_dead(self, tmp_path):
        """A template referenced by a FragmentContract should not be dead."""
        (tmp_path / "search.html").write_text("{% block results %}results{% endblock %}")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/search")
        @contract(returns=FragmentContract("search.html", "results"))
        async def search():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

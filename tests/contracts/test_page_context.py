"""Tests for Page context gap detection (check 9)."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import FragmentContract, Severity, check_hypermedia_surface, contract


class TestPageContextGaps:
    """Tests for Page context gap detection (check 9).

    When a route uses FragmentContract, the target block may only use
    a subset of the full template's variables.  Full-page Page renders
    evaluate the entire template, so missing variables cause runtime
    errors.  The checker should warn about this gap.
    """

    def test_gap_detected_when_extra_vars_in_other_blocks(self, tmp_path):
        """Template with two blocks where one uses vars the other doesn't."""
        (tmp_path / "page.html").write_text(
            "{% block detail %}{{ detail.name }}{% endblock %}"
            "{% block grid %}{{ pokemon }}{{ current_type }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/detail")
        @contract(returns=FragmentContract("page.html", "detail"))
        async def detail():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 1
        assert ctx_issues[0].severity == Severity.WARNING
        assert "current_type" in ctx_issues[0].message or "pokemon" in ctx_issues[0].message
        assert result.page_context_warnings == 1

    def test_no_gap_when_block_uses_all_vars(self, tmp_path):
        """When the block uses the same vars as the full template, no warning."""
        (tmp_path / "page.html").write_text(
            "{% block content %}{{ title }}{{ body }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("page.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0
        assert result.page_context_warnings == 0

    def test_no_gap_for_single_block_templates(self, tmp_path):
        """Template with just one block — no gap possible."""
        (tmp_path / "simple.html").write_text("{% block main %}<h1>{{ title }}</h1>{% endblock %}")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("simple.html", "main"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0

    def test_route_without_fragment_contract_skipped(self, tmp_path):
        """Routes without FragmentContract should not trigger this check."""
        (tmp_path / "page.html").write_text(
            "{% block a %}{{ x }}{% endblock %}{% block b %}{{ y }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0

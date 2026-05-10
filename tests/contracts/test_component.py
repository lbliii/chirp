"""Tests for Kida component call validation."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import Severity, check_hypermedia_surface


class TestComponentCallValidation:
    """Component call validation via Kida 0.9 static analysis."""

    def test_unknown_and_missing_params_surface_as_component_errors(self, tmp_path):
        """Bad Kida component call parameters fail app.check()."""
        (tmp_path / "board.html").write_text(
            """
            {% def card(title: str, url: str) %}<a href="{{ url }}">{{ title }}</a>{% end %}
            {{ card(titl="Save") }}
            """
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.ERROR
        assert "titl" in comp_issues[0].message
        assert "url" in comp_issues[0].message
        assert comp_issues[0].template == "board.html"
        assert "line" in (comp_issues[0].details or "")
        assert result.component_calls_validated == 1

    def test_literal_type_mismatch_surfaces_as_component_error(self, tmp_path):
        """Kida type annotations catch literal component argument mismatches."""
        (tmp_path / "board.html").write_text(
            """
            {% def badge(count: int) %}<span>{{ count }}</span>{% end %}
            {{ badge(count="5") }}
            """
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.ERROR
        assert "passes str" in comp_issues[0].message
        assert "expects int" in comp_issues[0].message

    def test_valid_component_calls_do_not_emit_component_issues(self, tmp_path):
        """Valid Kida component calls stay quiet."""
        (tmp_path / "board.html").write_text(
            """
            {% def card(title: str, url: str) %}<a href="{{ url }}">{{ title }}</a>{% end %}
            {{ card(title="Save", url="/save") }}
            """
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 0
        assert result.component_calls_validated == 0

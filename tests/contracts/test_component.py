"""Tests for component call validation via kida_env.validate_calls()."""

from types import SimpleNamespace

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import Severity, check_hypermedia_surface


class TestComponentCallValidation:
    """Component call validation via kida_env.validate_calls()."""

    def test_issues_surface_from_validate_calls(self, tmp_path):
        """When kida exposes validate_calls(), issues are forwarded."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        # Prepare mock issues from kida
        mock_issue = SimpleNamespace(
            is_error=True,
            message="card(titl='x') has no parameter 'titl'. Did you mean 'title'?",
            template="board.html",
        )

        app._ensure_frozen()
        kida_env = app._kida_env
        # Temporarily add validate_calls to the environment
        kida_env.validate_calls = lambda: [mock_issue]
        try:
            result = check_hypermedia_surface(app)
        finally:
            del kida_env.validate_calls

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.ERROR
        assert "titl" in comp_issues[0].message
        assert comp_issues[0].template == "board.html"
        assert result.component_calls_validated == 1

    def test_warning_severity_forwarded(self, tmp_path):
        """Non-error issues from validate_calls come through as WARNING."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        mock_issue = SimpleNamespace(
            is_error=False,
            message="card() missing optional parameter 'footer'.",
            template="board.html",
        )

        app._ensure_frozen()
        kida_env = app._kida_env
        kida_env.validate_calls = lambda: [mock_issue]
        try:
            result = check_hypermedia_surface(app)
        finally:
            del kida_env.validate_calls

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.WARNING

    def test_graceful_noop_without_validate_calls(self, tmp_path):
        """When kida doesn't have validate_calls, no component issues."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 0
        assert result.component_calls_validated == 0

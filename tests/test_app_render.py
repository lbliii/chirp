"""Tests for app.render() — programmatic Fragment/Template/InlineTemplate rendering."""

from pathlib import Path

from chirp import App
from chirp.config import AppConfig
from chirp.templating.returns import Fragment, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _app(**config_overrides: object) -> App:
    """Build an App wired to the test templates directory."""
    cfg = AppConfig(template_dir=TEMPLATES_DIR, **config_overrides)
    return App(config=cfg)


class TestAppRenderFragment:
    def test_render_fragment(self) -> None:
        app = _app()

        @app.route("/")
        def index():
            return "ok"

        html = app.render(Fragment("search.html", "results_list", results=["one", "two"]))
        assert '<div id="results">' in html
        assert "one" in html
        assert "two" in html
        assert "<form>" not in html

    def test_render_fragment_triggers_freeze(self) -> None:
        """render() triggers freeze on first call without explicit run."""
        app = _app()

        @app.route("/")
        def index():
            return "ok"

        assert not app._frozen
        html = app.render(Fragment("search.html", "results_list", results=[]))
        assert app._frozen
        assert '<div id="results">' in html


class TestAppRenderTemplate:
    def test_render_template(self) -> None:
        app = _app()

        @app.route("/")
        def index():
            return "ok"

        html = app.render(Template("page.html", title="Home"))
        assert "<title>Home</title>" in html
        assert "<h1>Home</h1>" in html

    def test_render_template_with_list(self) -> None:
        app = _app()

        html = app.render(
            Template("page.html", title="List", items=["a", "b", "c"])
        )
        assert "<li>a</li>" in html
        assert "<li>b</li>" in html
        assert "<li>c</li>" in html


class TestAppRenderInlineTemplate:
    def test_render_inline_template(self) -> None:
        app = _app()

        html = app.render(Template.inline("<h1>{{ title }}</h1>", title="Hello"))
        assert "<h1>Hello</h1>" in html

    def test_render_inline_template_no_context(self) -> None:
        app = _app()

        html = app.render(Template.inline("<p>static</p>"))
        assert "<p>static</p>" in html

    def test_render_inline_template_works_without_template_dir(self) -> None:
        """InlineTemplate works even when app has no template_dir (minimal env)."""
        app = App(config=AppConfig(template_dir="nonexistent"))

        @app.route("/")
        def index():
            return "ok"

        html = app.render(Template.inline("<b>{{ x }}</b>", x="bold"))
        assert "<b>bold</b>" in html


class TestAppRenderWithCustomEnv:
    def test_render_fragment_with_custom_env(self) -> None:
        """Fragment works with custom kida_env that has the template."""
        from kida import DictLoader, Environment

        env = Environment(
            loader=DictLoader({
                "custom.html": "{% block content %}CUSTOM {{ x }}{% endblock %}",
            })
        )
        app = App(kida_env=env)

        @app.route("/")
        def index():
            return "ok"

        html = app.render(Fragment("custom.html", "content", x="value"))
        assert "CUSTOM value" in html

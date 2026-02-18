"""Tests for InlineTemplate — Template.inline() and negotiation rendering."""

import pytest
from kida import Environment

from chirp.server.negotiation import negotiate
from chirp.templating.returns import InlineTemplate, Template


class TestInlineTemplateType:
    def test_inline_returns_inline_template(self) -> None:
        result = Template.inline("<h1>{{ title }}</h1>", title="Hello")
        assert isinstance(result, InlineTemplate)

    def test_inline_template_source(self) -> None:
        it = Template.inline("<p>{{ msg }}</p>", msg="hi")
        assert it.source == "<p>{{ msg }}</p>"
        assert it.context == {"msg": "hi"}

    def test_inline_template_no_context(self) -> None:
        it = Template.inline("<p>static</p>")
        assert it.context == {}

    def test_inline_template_frozen(self) -> None:
        it = Template.inline("<p>hi</p>")
        with pytest.raises(AttributeError):
            it.source = "other"  # type: ignore[misc]


class TestInlineTemplateNegotiation:
    def test_renders_to_html(self) -> None:
        it = InlineTemplate("<h1>{{ greeting }}</h1>", greeting="Hello")
        response = negotiate(it)
        assert response.status == 200
        assert "text/html" in response.content_type
        assert "<h1>Hello</h1>" in response.text

    def test_renders_without_kida_env(self) -> None:
        """InlineTemplate works even when no template_dir is configured."""
        it = InlineTemplate("<p>{{ x }}</p>", x="works")
        response = negotiate(it, kida_env=None)
        assert "<p>works</p>" in response.text

    def test_renders_with_kida_env(self) -> None:
        """InlineTemplate uses the provided kida env when available."""
        env = Environment()
        it = InlineTemplate("<b>{{ v }}</b>", v="bold")
        response = negotiate(it, kida_env=env)
        assert "<b>bold</b>" in response.text


class TestInlineTemplateTopLevelImport:
    def test_import_from_chirp(self) -> None:
        import chirp

        assert chirp.InlineTemplate is InlineTemplate


class TestInlineTemplateContractWarning:
    def test_check_warns_about_inline_template(self) -> None:
        """app.check() should warn when a route returns InlineTemplate."""
        from chirp.app import App
        from chirp.contracts import Severity, check_hypermedia_surface

        app = App()

        @app.route("/proto")
        async def proto() -> InlineTemplate:
            return Template.inline("<p>hi</p>")

        app._ensure_frozen()
        result = check_hypermedia_surface(app)

        inline_warnings = [i for i in result.issues if i.category == "inline_template"]
        assert len(inline_warnings) == 1
        assert inline_warnings[0].severity == Severity.WARNING
        assert "/proto" in inline_warnings[0].message

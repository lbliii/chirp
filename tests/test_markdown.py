"""Tests for chirp.markdown — renderer, filter registration, error handling."""

from __future__ import annotations

import pytest


# ── MarkdownRenderer ─────────────────────────────────────────────────────


class TestMarkdownRenderer:
    """Test the core MarkdownRenderer wrapper over patitas."""

    def test_renders_heading(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("# Hello")
        assert "<h1" in html
        assert "Hello" in html

    def test_renders_paragraph(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("Hello, world!")
        assert "<p>" in html
        assert "Hello, world!" in html

    def test_renders_emphasis(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("**bold** and *italic*")
        assert "<strong>" in html
        assert "<em>" in html

    def test_empty_source_returns_empty(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        assert md.render("") == ""

    def test_renders_fenced_code(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("```python\nprint('hi')\n```")
        assert "<code" in html
        assert "print" in html

    def test_renders_list(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("- one\n- two\n- three")
        assert "<li>" in html
        assert "one" in html


# ── Plugins ──────────────────────────────────────────────────────────────


class TestPlugins:
    """Test that patitas plugins are forwarded correctly."""

    def test_strikethrough_with_plugin(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer(plugins=["strikethrough"])
        html = md.render("~~deleted~~")
        assert "<del>" in html

    def test_task_lists_with_plugin(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer(plugins=["task_lists"])
        html = md.render("- [x] done\n- [ ] todo")
        assert 'type="checkbox"' in html

    def test_default_plugins_none(self) -> None:
        """With no plugins, basic markdown still renders."""
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer(plugins=None)
        html = md.render("# Hello\n\n**bold**")
        assert "<h1" in html
        assert "<strong>" in html

    def test_multiple_plugins(self) -> None:
        from chirp.markdown import MarkdownRenderer

        md = MarkdownRenderer(plugins=["strikethrough", "task_lists"])
        html = md.render("~~deleted~~")
        assert "<del>" in html


# ── Error Handling ───────────────────────────────────────────────────────


class TestErrorHandling:
    """Test error messages when patitas is not installed."""

    def test_error_is_chirp_error_subclass(self) -> None:
        from chirp.errors import ChirpError
        from chirp.markdown.errors import MarkdownError, MarkdownNotInstalledError

        assert issubclass(MarkdownError, ChirpError)
        assert issubclass(MarkdownNotInstalledError, MarkdownError)

    def test_error_message_mentions_pip_install(self) -> None:
        from chirp.markdown.errors import MarkdownNotInstalledError

        err = MarkdownNotInstalledError("chirp.markdown requires 'patitas'")
        assert "patitas" in str(err)


# ── Filter Registration ─────────────────────────────────────────────────


class TestFilterRegistration:
    """Test register_markdown_filter wires the filter onto the app."""

    def test_registers_filter_on_app(self) -> None:
        from chirp import App
        from chirp.markdown import register_markdown_filter

        app = App()
        renderer = register_markdown_filter(app)

        assert renderer is not None
        # The filter should be registered in the app's internal filter dict
        assert "markdown" in app._template_filters

    def test_filter_function_renders_markdown(self) -> None:
        from chirp import App
        from chirp.markdown import register_markdown_filter

        app = App()
        register_markdown_filter(app)

        # The registered filter should produce HTML
        filter_fn = app._template_filters["markdown"]
        html = filter_fn("# Hello")
        assert "<h1" in html

    def test_custom_filter_name(self) -> None:
        from chirp import App
        from chirp.markdown import register_markdown_filter

        app = App()
        register_markdown_filter(app, filter_name="md")

        assert "md" in app._template_filters
        assert "markdown" not in app._template_filters

    def test_returns_renderer_for_direct_use(self) -> None:
        from chirp import App
        from chirp.markdown import MarkdownRenderer, register_markdown_filter

        app = App()
        renderer = register_markdown_filter(app)

        assert isinstance(renderer, MarkdownRenderer)
        html = renderer.render("**bold**")
        assert "<strong>" in html


# ── Lazy Import ──────────────────────────────────────────────────────────


class TestLazyImport:
    """Test that MarkdownRenderer is accessible from the top-level chirp package."""

    def test_import_from_chirp(self) -> None:
        from chirp import MarkdownRenderer

        md = MarkdownRenderer()
        html = md.render("# Test")
        assert "<h1" in html

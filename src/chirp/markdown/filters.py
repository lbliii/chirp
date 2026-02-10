"""Template filter registration for Markdown rendering.

Provides a one-liner to register a ``markdown`` filter on a chirp App
so that templates can use ``{{ content | markdown }}``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chirp.markdown.renderer import MarkdownRenderer

if TYPE_CHECKING:
    from chirp.app import App


def register_markdown_filter(
    app: App,
    *,
    plugins: list[str] | None = None,
    highlight: bool = False,
    filter_name: str = "markdown",
) -> MarkdownRenderer:
    """Register a ``markdown`` template filter on the app.

    Creates a ``MarkdownRenderer`` and registers its ``render`` method
    as a kida template filter.  Returns the renderer so callers can
    also use it directly (e.g., in route handlers).

    Usage::

        from chirp.markdown import register_markdown_filter

        app = App()
        md = register_markdown_filter(app)

        # In templates: {{ content | markdown }}
        # In code:      html = md.render("# Hello")

    Args:
        app: The chirp application to register the filter on.
        plugins: Patitas plugins to enable (default: all).
        highlight: Enable syntax highlighting for fenced code blocks.
        filter_name: Template filter name (default: ``"markdown"``).

    Returns:
        The ``MarkdownRenderer`` instance backing the filter.
    """
    renderer = MarkdownRenderer(plugins=plugins, highlight=highlight)
    app.template_filter(filter_name)(renderer.render)
    return renderer

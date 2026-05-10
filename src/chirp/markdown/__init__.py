"""Markdown rendering for chirp via patitas.

Parse and render Markdown to HTML in templates, routes, and SSE streams.
Thin wrapper around patitas with chirp-specific ergonomics.

Basic usage::

    from chirp.markdown import register_markdown_filter

    app = App()
    register_markdown_filter(app)

Then in templates::

    {{ content | markdown }}

Rendered markdown is sanitized by default. Use ``sanitize=False`` only for
trusted markdown or controlled CMS content where raw HTML is intentional.

Requires ``patitas`` (includes rosettes for syntax highlighting)::

    pip install chirp[markdown]
"""

from chirp.markdown.errors import MarkdownError, MarkdownNotInstalledError
from chirp.markdown.filters import register_markdown_filter
from chirp.markdown.renderer import MarkdownRenderer

__all__ = [
    "MarkdownError",
    "MarkdownNotInstalledError",
    "MarkdownRenderer",
    "register_markdown_filter",
]

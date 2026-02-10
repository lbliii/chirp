"""Core markdown renderer wrapping patitas.

Provides a stateful renderer that can be used directly or registered
as a template filter.  The interface is designed so that incremental
parsing can be added behind it later without changing downstream code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chirp.markdown.errors import MarkdownNotInstalledError

if TYPE_CHECKING:
    from patitas import Markdown


class MarkdownRenderer:
    """Render Markdown source to HTML via patitas.

    Wraps ``patitas.Markdown`` with a stable interface that chirp
    controls.  Phase 1 does a full parse+render on every call.
    Incremental parsing can be layered in later behind ``render()``.

    Args:
        plugins: Patitas plugins to enable (default: all).
        highlight: Enable syntax highlighting for fenced code blocks.
    """

    def __init__(
        self,
        *,
        plugins: list[str] | None = None,
        highlight: bool = False,
    ) -> None:
        self._md: Markdown = _get_markdown(plugins=plugins, highlight=highlight)

    def render(self, source: str) -> str:
        """Render Markdown source to an HTML string.

        Args:
            source: Raw Markdown text.

        Returns:
            Rendered HTML.
        """
        if not source:
            return ""
        return self._md(source)


def _get_markdown(
    *,
    plugins: list[str] | None,
    highlight: bool,
) -> Markdown:
    """Create a patitas Markdown instance, raising a clear error if missing."""
    try:
        from patitas import Markdown
    except ImportError:
        msg = (
            "chirp.markdown requires 'patitas' for Markdown rendering. "
            "Install with: pip install chirp[markdown]"
        )
        raise MarkdownNotInstalledError(msg) from None

    return Markdown(plugins=plugins or ["all"], highlight=highlight)

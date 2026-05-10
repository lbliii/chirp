"""Core markdown renderer wrapping patitas.

Provides a stateful renderer that can be used directly or registered
as a template filter.  The interface is designed so that incremental
parsing can be added behind it later without changing downstream code.
"""

from html import escape
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from kida.template import Markup

from chirp.markdown.errors import MarkdownNotInstalledError

_ALLOWED_TAGS = frozenset(
    {
        "a",
        "abbr",
        "b",
        "blockquote",
        "br",
        "code",
        "del",
        "details",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "input",
        "kbd",
        "li",
        "mark",
        "ol",
        "p",
        "pre",
        "s",
        "span",
        "strong",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_VOID_TAGS = frozenset({"br", "hr", "img", "input"})
_ALLOWED_ATTRS = frozenset(
    {
        "alt",
        "checked",
        "class",
        "colspan",
        "disabled",
        "height",
        "href",
        "id",
        "loading",
        "rel",
        "rowspan",
        "src",
        "target",
        "title",
        "type",
        "width",
    }
)
_URL_ATTRS = frozenset({"href", "src"})
_ALLOWED_URL_SCHEMES = frozenset({"", "http", "https", "mailto", "tel"})

if TYPE_CHECKING:
    from patitas import Markdown


class MarkdownRenderer:
    """Render Markdown source to HTML via patitas.

    Wraps ``patitas.Markdown`` with a stable interface that chirp
    controls.  Phase 1 does a full parse+render on every call.
    Incremental parsing can be layered in later behind ``render()``.

    Args:
        plugins: Patitas plugins to enable (default: all).
        highlight: Enable syntax highlighting for fenced code blocks (default: True).
    """

    def __init__(
        self,
        *,
        plugins: list[str] | None = None,
        highlight: bool = True,
        sanitize: bool = True,
    ) -> None:
        self._md: Markdown = _get_markdown(plugins=plugins, highlight=highlight)
        self._sanitize = sanitize

    def render(self, source: str) -> Markup:
        """Render Markdown source to an HTML string.

        Returns sanitized ``Markup`` so kida's auto-escaping preserves
        Markdown-generated HTML when the renderer is used as a template
        filter. Pass ``sanitize=False`` only for trusted content.

        Args:
            source: Raw Markdown text.

        Returns:
            Rendered HTML wrapped in ``Markup``.
        """
        if not source:
            return Markup("")
        html = str(self._md(source))
        if self._sanitize:
            html = _sanitize_html(html)
        return Markup(html)


def _sanitize_html(html: str) -> str:
    sanitizer = _MarkdownHTMLSanitizer()
    sanitizer.feed(html)
    sanitizer.close()
    return sanitizer.html


class _MarkdownHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._skip_depth = 0

    @property
    def html(self) -> str:
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return
        rendered_attrs = self._render_attrs(tag, attrs)
        suffix = " /" if tag in _VOID_TAGS else ""
        self._parts.append(f"<{tag}{rendered_attrs}{suffix}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if not self._skip_depth:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip_depth:
            self._parts.append(f"&#{name};")

    def _render_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        rendered: list[tuple[str, str | None]] = []
        rel_index: int | None = None
        target_blank = False
        for name, value in attrs:
            name = name.lower()
            if not _is_allowed_attr(name):
                continue
            if tag == "input" and name not in {"type", "checked", "disabled"}:
                continue
            if value is None:
                rendered.append((name, None))
                continue
            if name in _URL_ATTRS and not _is_safe_url(value):
                continue
            if tag == "a" and name == "target" and value == "_blank":
                target_blank = True
            if tag == "a" and name == "rel":
                rel_index = len(rendered)
            rendered.append((name, value))
        if tag == "a" and target_blank:
            rel_value = "noopener noreferrer"
            if rel_index is None:
                rendered.append(("rel", rel_value))
            else:
                existing = rendered[rel_index][1] or ""
                rel_tokens = [token for token in existing.split() if token]
                seen = {token.lower() for token in rel_tokens}
                rel_tokens.extend(
                    token for token in ("noopener", "noreferrer") if token not in seen
                )
                rendered[rel_index] = ("rel", " ".join(rel_tokens))
        if not rendered:
            return ""
        return " " + " ".join(
            name if value is None else f'{name}="{escape(value, quote=True)}"'
            for name, value in rendered
        )


def _is_allowed_attr(name: str) -> bool:
    return name in _ALLOWED_ATTRS or name.startswith(("aria-", "data-"))


def _is_safe_url(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "/", "./", "../")):
        return True
    parsed = urlsplit(stripped)
    return parsed.scheme.lower() in _ALLOWED_URL_SCHEMES


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

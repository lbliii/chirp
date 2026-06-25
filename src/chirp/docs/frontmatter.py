"""YAML frontmatter parser for markdown documentation files.

Parses the ``---`` delimited YAML header from markdown files.  Missing
frontmatter is handled gracefully: title is derived from the first
``#`` heading, and all other fields use defaults.
"""

from __future__ import annotations

import re
from pathlib import Path

from kida.template import Markup

from chirp.docs.models import DocBlock, DocMetadata, DocPage, DocSource, TocEntry

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)", re.MULTILINE)

_HTML_HEADING_RE = re.compile(
    r'<h([1-6])(?:\s+id="([^"]*)")?[^>]*>(.*?)</h\1>',
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split frontmatter from markdown body.

    Returns:
        A (metadata_dict, body) tuple.  If no frontmatter is found
        the metadata dict is empty and body is the full text.
    """
    from patitas.frontmatter import parse_frontmatter as patitas_parse_frontmatter

    meta, body = patitas_parse_frontmatter(text)
    if not isinstance(meta, dict):
        return {}, body
    return meta, body


def _meta_from_dict(d: dict[str, object]) -> DocMetadata:
    """Build a ``DocMetadata`` from a parsed frontmatter dict."""
    tags_raw = d.get("tags", ())
    if isinstance(tags_raw, str):
        tags = frozenset(t.strip() for t in tags_raw.split(",") if t.strip())
    elif isinstance(tags_raw, list):
        tags = frozenset(str(t) for t in tags_raw)
    else:
        tags = frozenset()

    order_val = d.get("order", 999)
    if isinstance(order_val, float) and order_val.is_integer():
        order = int(order_val)
    elif isinstance(order_val, int):
        order = order_val
    else:
        order = int(str(order_val))
    return DocMetadata(
        order=order,
        category=str(d.get("category", "")),
        tags=tags,
        description=str(d.get("description", "")),
        draft=bool(d.get("draft", False)),
    )


def _title_from_body(body: str) -> str:
    """Extract title from first markdown heading, or return empty string."""
    m = _HEADING_RE.search(body)
    return m.group(1).strip() if m else ""


def _extract_toc(html: str) -> tuple[TocEntry, ...]:
    """Extract table-of-contents entries from rendered HTML headings."""
    entries: list[TocEntry] = []
    for m in _HTML_HEADING_RE.finditer(html):
        level = int(m.group(1))
        heading_id = m.group(2) or ""
        text = _TAG_RE.sub("", m.group(3)).strip()
        entries.append(TocEntry(level=level, id=heading_id, text=text))
    return tuple(entries)


_IDENT_CLEAN_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _slug_to_identifier(s: str) -> str:
    """Convert kebab-case (or arbitrary text) to a snake_case Python identifier.

    Kida block names must be valid Python identifiers, while heading ids
    emitted by patitas are kebab-case (``section-overview``).
    """
    cleaned = _IDENT_CLEAN_RE.sub("_", s).strip("_").lower()
    if not cleaned:
        return "section"
    if cleaned[0].isdigit():
        cleaned = "s_" + cleaned
    return cleaned


def _split_blocks(html: str) -> tuple[DocBlock, ...]:
    """Split rendered HTML into sections at H2 (or H3 fallback) boundaries.

    Content before the first heading becomes a synthesized ``intro`` block
    (``depth=0``, empty ``heading``/``anchor``).  Duplicate ids are
    disambiguated with a numeric suffix.
    """
    matches = list(_HTML_HEADING_RE.finditer(html))

    boundary_level: int | None = None
    for lvl in (2, 3):
        if any(int(m.group(1)) == lvl for m in matches):
            boundary_level = lvl
            break

    if boundary_level is None:
        if html.strip():
            return (DocBlock(id="intro", heading="", html=Markup(html), depth=0, anchor=""),)
        return ()

    boundaries = [m for m in matches if int(m.group(1)) == boundary_level]
    blocks: list[DocBlock] = []
    seen_ids: dict[str, int] = {}

    def _unique(base: str) -> str:
        if base not in seen_ids:
            seen_ids[base] = 1
            return base
        seen_ids[base] += 1
        return f"{base}_{seen_ids[base]}"

    intro_html = html[: boundaries[0].start()]
    if intro_html.strip():
        blocks.append(
            DocBlock(
                id=_unique("intro"),
                heading="",
                html=Markup(intro_html),
                depth=0,
                anchor="",
            )
        )

    for i, m in enumerate(boundaries):
        start = m.start()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(html)
        anchor = m.group(2) or ""
        heading_text = _TAG_RE.sub("", m.group(3)).strip()
        base_id = _slug_to_identifier(anchor or heading_text)
        blocks.append(
            DocBlock(
                id=_unique(base_id),
                heading=heading_text,
                html=Markup(html[start:end]),
                depth=boundary_level,
                anchor=anchor,
            )
        )
    return tuple(blocks)


_INDEX_STEMS = frozenset({"index", "_index", "README"})


def _slug_from_path(md_path: Path, content_dir: Path) -> str:
    """Derive a URL slug from a file path relative to content_dir.

    Index-like files become the parent directory slug:

    ``content_dir/guides/getting-started.md`` → ``guides/getting-started``
    ``content_dir/guides/index.md``           → ``guides``
    ``content_dir/guides/_index.md``          → ``guides``
    ``content_dir/guides/README.md``          → ``guides``
    ``content_dir/index.md``                  → ``index``
    ``content_dir/_index.md``                 → ``index``
    """
    rel = md_path.relative_to(content_dir)
    slug = str(rel.with_suffix("")).replace("\\", "/")

    # Normalize index files to parent directory slug
    stem = md_path.stem
    if stem in _INDEX_STEMS:
        parent = str(rel.parent).replace("\\", "/")
        if parent == ".":
            # Root-level index → "index" (the site landing page)
            return "index"
        return parent

    return slug


def parse_file(md_path: Path, content_dir: Path) -> DocPage:
    """Parse a single markdown file into a ``DocPage``.

    Reads the file, splits frontmatter, renders markdown via
    ``MarkdownRenderer``, and extracts TOC entries.
    """
    from chirp.markdown import MarkdownRenderer

    text = md_path.read_text(encoding="utf-8")
    meta_dict, body = parse_frontmatter(text)
    metadata = _meta_from_dict(meta_dict)

    title = str(meta_dict.get("title", "")) or _title_from_body(body)
    slug = _slug_from_path(md_path, content_dir)

    renderer = MarkdownRenderer()
    html = renderer.render(body)
    html_str = str(html)
    toc = _extract_toc(html_str)
    blocks = _split_blocks(html_str)

    return DocPage(
        slug=slug,
        title=title,
        raw=body,
        html=html,
        toc=toc,
        metadata=metadata,
        source=DocSource.MARKDOWN,
        source_path=md_path,
        blocks=blocks,
    )

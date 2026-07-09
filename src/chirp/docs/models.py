"""Frozen dataclasses for the docs module.

All types are immutable and thread-safe.  ``DocPage`` is the universal
unit — hand-written markdown and autodoc-generated pages share the same
type so the collection, search, templates, and tools treat them
identically.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kida.template import Markup


class DocSource(enum.Enum):
    """Where a ``DocPage`` originated."""

    MARKDOWN = "markdown"
    AUTODOC = "autodoc"


@dataclass(frozen=True, slots=True)
class TocEntry:
    """A single heading extracted from rendered HTML."""

    level: int
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class DocBlock:
    """One section of a doc page, split at an H2 (or H3) boundary.

    ``id`` is a snake_case identifier suitable for a kida block name
    (``section_<id>``).  ``anchor`` is the original kebab-case heading id
    preserved for URL fragments (``#section-overview``).  Content before
    the first heading becomes a synthesized ``intro`` block with
    ``depth=0``.
    """

    id: str
    heading: str
    html: Markup
    depth: int
    anchor: str


@dataclass(frozen=True, slots=True)
class DocMetadata:
    """Frontmatter fields parsed from a markdown file header."""

    order: int = 999
    category: str = ""
    tags: frozenset[str] = frozenset()
    description: str = ""
    draft: bool = False


@dataclass(frozen=True, slots=True)
class DocPage:
    """One documentation page — the universal unit of the docs module.

    Both hand-written markdown files and autodoc-generated reference
    pages produce ``DocPage`` instances.  Templates, search, and tools
    operate on this type exclusively.
    """

    slug: str
    title: str
    raw: str
    html: Markup
    toc: tuple[TocEntry, ...]
    metadata: DocMetadata
    source: DocSource
    source_path: Path | None = None
    blocks: tuple[DocBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class NavGroup:
    """A group of pages for sidebar navigation.

    When a category directory contains an index file (``index.md``,
    ``_index.md``, or ``README.md``), it becomes the ``landing_page``
    and the category heading links to it.
    """

    category: str
    pages: tuple[DocPage, ...]
    landing_page: DocPage | None = None


@dataclass(frozen=True, slots=True)
class ParamDoc:
    """One parameter in a route or tool signature."""

    name: str
    type_str: str
    required: bool
    description: str = ""
    default: str | None = None


@dataclass(frozen=True, slots=True)
class RouteDoc:
    """Autodoc-generated from a single ``Route``.

    ``query_media_types`` carries normalized accepted request media ranges for
    provisional HTTP QUERY routes and remains ``None`` for ordinary routes.
    """

    path: str
    methods: frozenset[str]
    handler_name: str
    docstring: str | None
    parameters: tuple[ParamDoc, ...]
    template: str | None = None
    layout_chain: tuple[str, ...] | None = None
    query_media_types: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ToolDoc:
    """Autodoc-generated from a single registered tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    parameters: tuple[ParamDoc, ...]

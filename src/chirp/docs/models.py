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


@dataclass(frozen=True, slots=True)
class NavGroup:
    """A group of pages for sidebar navigation."""

    category: str
    pages: tuple[DocPage, ...]


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
    """Autodoc-generated from a single ``Route``."""

    path: str
    methods: frozenset[str]
    handler_name: str
    docstring: str | None
    parameters: tuple[ParamDoc, ...]
    template: str | None = None
    layout_chain: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ToolDoc:
    """Autodoc-generated from a single registered tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    parameters: tuple[ParamDoc, ...]

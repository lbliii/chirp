"""Docs as a feature — serve markdown and auto-generated API reference.

Load markdown files at startup, render once via patitas, and serve
through Kida templates with fragment navigation.  Optionally introspect
the frozen app to generate API reference pages (autodoc).

Basic usage::

    from chirp.docs import DocsPlugin

    app.mount("/docs", DocsPlugin(content_dir="./content/docs"))

Requires ``patitas`` (``pip install bengal-chirp[markdown]``).
"""

from chirp.docs.collection import DocsCollection
from chirp.docs.models import (
    DocMetadata,
    DocPage,
    DocSource,
    NavGroup,
    ParamDoc,
    RouteDoc,
    TocEntry,
    ToolDoc,
)
from chirp.docs.plugin import DocsPlugin

__all__ = [
    "DocMetadata",
    "DocPage",
    "DocSource",
    "DocsCollection",
    "DocsPlugin",
    "NavGroup",
    "ParamDoc",
    "RouteDoc",
    "TocEntry",
    "ToolDoc",
]

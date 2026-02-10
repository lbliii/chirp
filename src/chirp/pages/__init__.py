"""Filesystem-based routing with automatic layout nesting.

Combines co-located routes and templates, automatic layout composition,
and htmx-header-driven rendering depth.  The ``pages/`` directory
structure defines URL paths, layout nesting, and context inheritance.

Usage::

    app = App(AppConfig(template_dir="pages"))
    app.mount_pages("pages")
    app.run()

Conventions:

    pages/
      _layout.html       # Root layout (target: body)
      _context.py        # Root context provider
      documents/
        page.py          # GET /documents
        {doc_id}/
          _layout.html   # Nested layout (target: app-content)
          _context.py    # Context: loads doc
          page.py        # GET /documents/{doc_id}
          edit.py        # POST /documents/{doc_id}/edit
"""

from chirp.pages.discovery import discover_pages
from chirp.pages.reactive import (
    BlockRef,
    ChangeEvent,
    DependencyIndex,
    ReactiveBus,
    reactive_stream,
)
from chirp.pages.renderer import render_with_layouts
from chirp.pages.types import ContextProvider, LayoutChain, LayoutInfo, PageRoute

__all__ = [
    "BlockRef",
    "ChangeEvent",
    "ContextProvider",
    "DependencyIndex",
    "LayoutChain",
    "LayoutInfo",
    "PageRoute",
    "ReactiveBus",
    "discover_pages",
    "reactive_stream",
    "render_with_layouts",
]

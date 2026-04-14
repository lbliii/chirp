"""MCP tool definitions for AI agent access to documentation.

Three tools expose the ``DocsCollection`` to agents:

- ``search_docs(query)`` — keyword search across all pages
- ``get_doc(slug)`` — retrieve a specific page by slug
- ``list_docs(category?)`` — list pages, optionally filtered by category

All tools return raw markdown (not HTML) in the ``content`` field —
more useful for LLM consumption.

These functions are factories that close over a ``_CollectionHolder``
so they see the live collection (including autodoc pages merged at
startup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.docs.plugin import _CollectionHolder


def make_search_docs(holder: _CollectionHolder):
    """Create a ``search_docs`` tool function bound to the collection."""

    def search_docs(query: str) -> list[dict]:
        """Search documentation by keyword. Returns matching pages ranked by relevance."""
        results = holder.collection.search(query)
        return [
            {
                "slug": page.slug,
                "title": page.title,
                "content": page.raw,
                "source": page.source.value,
                "category": page.metadata.category,
                "description": page.metadata.description,
            }
            for page in results
        ]

    return search_docs


def make_get_doc(holder: _CollectionHolder):
    """Create a ``get_doc`` tool function bound to the collection."""

    def get_doc(slug: str) -> dict:
        """Retrieve a specific documentation page by slug. Returns full content."""
        page = holder.collection.get(slug)
        if page is None:
            return {"error": f"Document not found: {slug}"}
        return {
            "slug": page.slug,
            "title": page.title,
            "content": page.raw,
            "source": page.source.value,
            "category": page.metadata.category,
            "description": page.metadata.description,
        }

    return get_doc


def make_list_docs(holder: _CollectionHolder):
    """Create a ``list_docs`` tool function bound to the collection."""

    def list_docs(category: str | None = None) -> list[dict]:
        """List documentation pages. Optionally filter by category."""
        pages = holder.collection.list(category=category)
        return [
            {
                "slug": page.slug,
                "title": page.title,
                "source": page.source.value,
                "category": page.metadata.category,
                "description": page.metadata.description,
            }
            for page in pages
        ]

    return list_docs

"""DocsPlugin — mount documentation as browsable pages at any URL prefix.

Usage::

    from chirp.docs import DocsPlugin

    app.mount("/docs", DocsPlugin(content_dir="./content/docs"))

Registers routes for the index and individual doc pages, a template
loader for default templates, the markdown filter, and a nav template
global.  Fragment navigation works automatically via ``Page``.

When ``autodoc=True``, a startup hook introspects the frozen app and
merges auto-generated API reference pages into the collection.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kida import PackageLoader

from chirp.docs.collection import DocsCollection
from chirp.markdown import register_markdown_filter
from chirp.templating.returns import Page, Template

if TYPE_CHECKING:
    from chirp.app import App

_TEMPLATE_NS = "chirp_docs"


class _CollectionHolder:
    """Mutable wrapper so startup hook can replace the collection.

    Route closures capture this holder — when autodoc merges pages,
    the updated collection is visible to subsequent requests.
    """

    __slots__ = ("collection",)

    def __init__(self, collection: DocsCollection) -> None:
        self.collection = collection


class DocsPlugin:
    """Serve markdown documentation as first-class Chirp pages.

    Args:
        content_dir: Path to the directory containing ``.md`` files.
        title: Title shown on the docs index page.
        include_drafts: If ``True``, draft pages are included.
        autodoc: If ``True`` (default), generate API reference from
            the frozen app state after freeze.
        tools: If ``True`` (default), register MCP tools for AI agent
            access.  (Sprint 4 — not yet implemented.)
    """

    __slots__ = ("_autodoc", "_content_dir", "_include_drafts", "_title", "_tools")

    def __init__(
        self,
        content_dir: str | Path,
        *,
        title: str = "Documentation",
        include_drafts: bool = False,
        autodoc: bool = True,
        tools: bool = True,
    ) -> None:
        self._content_dir = Path(content_dir)
        self._title = title
        self._include_drafts = include_drafts
        self._autodoc = autodoc
        self._tools = tools

    def register(self, app: App, prefix: str) -> None:
        """Wire routes, templates, filters, and globals into the app."""
        markdown_collection = DocsCollection.load(
            self._content_dir,
            include_drafts=self._include_drafts,
        )
        holder = _CollectionHolder(markdown_collection)
        title = self._title

        # Register template loader for default docs templates
        app.add_loader(PackageLoader("chirp.docs", "templates"))

        # Register markdown filter (idempotent — safe to call multiple times)
        register_markdown_filter(app)

        # Template global: navigation items (returns live nav from holder)
        app.template_global("docs_nav_items")(lambda: holder.collection.as_nav())

        # -- Autodoc startup hook --
        if self._autodoc:

            @app.on_startup
            def _merge_autodoc() -> None:
                from chirp.docs.autodoc import generate_autodoc

                autodoc_pages = generate_autodoc(app)
                if autodoc_pages:
                    autodoc_collection = DocsCollection(autodoc_pages)
                    holder.collection = holder.collection.merge(autodoc_collection)

        # -- Routes --

        normalized_prefix = "/" + prefix.strip("/")

        @app.route(f"{normalized_prefix}/")
        def docs_index():
            return Template(
                f"{_TEMPLATE_NS}/doc_list.html",
                docs_title=title,
                docs_nav_items=holder.collection.as_nav(),
                docs_prefix=normalized_prefix,
            )

        @app.route(f"{normalized_prefix}/{{slug:path}}")
        def docs_page(slug: str):
            doc = holder.collection.get(slug)
            if doc is None:
                from chirp.errors import NotFound

                raise NotFound()
            return Page(
                f"{_TEMPLATE_NS}/doc_page.html",
                "doc_content",
                doc=doc,
                docs_nav_items=holder.collection.as_nav(),
                docs_prefix=normalized_prefix,
            )

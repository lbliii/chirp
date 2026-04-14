"""DocsPlugin — mount documentation as browsable pages at any URL prefix.

Usage::

    from chirp.docs import DocsPlugin

    app.mount("/docs", DocsPlugin(content_dir="./content/docs"))

Registers routes for the index and individual doc pages, a template
loader for default templates, the markdown filter, and a nav template
global.  Fragment navigation works automatically via ``Page``.

When ``autodoc=True``, a startup hook introspects the frozen app and
merges auto-generated API reference pages into the collection.

When ``suspense=True``, doc page routes use Suspense rendering — the
shell (sidebar, nav) renders immediately and the content block streams
in via OOB swap.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kida import PackageLoader

from chirp.docs.collection import DocsCollection
from chirp.markdown import register_markdown_filter
from chirp.templating.returns import Fragment, Page, Suspense, Template

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
            access.
        suspense: If ``True``, doc pages use Suspense rendering — the
            shell renders immediately, content streams in via OOB swap.
    """

    __slots__ = (
        "_autodoc",
        "_content_dir",
        "_include_drafts",
        "_suspense",
        "_title",
        "_tools",
    )

    def __init__(
        self,
        content_dir: str | Path,
        *,
        title: str = "Documentation",
        include_drafts: bool = False,
        autodoc: bool = True,
        tools: bool = True,
        suspense: bool = False,
    ) -> None:
        self._content_dir = Path(content_dir)
        self._title = title
        self._include_drafts = include_drafts
        self._autodoc = autodoc
        self._tools = tools
        self._suspense = suspense

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

        # Template globals: navigation items (returns live nav from holder)
        # docs_nav_items — callable, usable from any template in the app
        app.template_global("docs_nav_items")(lambda: holder.collection.as_nav())
        # docs_nav — alias, same callable
        app.template_global("docs_nav")(lambda: holder.collection.as_nav())

        # -- Contract checks --
        from chirp.docs.checks import (
            check_docs_cross_references,
            check_docs_no_drafts_exposed,
            check_docs_no_duplicate_slugs,
            check_docs_parseable,
        )

        normalized_prefix = "/" + prefix.strip("/")

        # Pass docs-specific data to checks via extras.
        # The holder is passed so checks see the live collection
        # (including autodoc pages merged at startup).
        app.set_contract_check_data("docs_content_dir", self._content_dir)
        app.set_contract_check_data("docs_prefix", normalized_prefix)
        app.set_contract_check_data("docs_include_drafts", self._include_drafts)
        app.set_contract_check_data("docs_holder", holder)

        app.register_contract_check(check_docs_parseable)
        app.register_contract_check(check_docs_no_duplicate_slugs)
        app.register_contract_check(check_docs_cross_references)
        app.register_contract_check(check_docs_no_drafts_exposed)

        # -- Autodoc startup hook --
        if self._autodoc:

            @app.on_startup
            def _merge_autodoc() -> None:
                from chirp.docs.autodoc import generate_autodoc

                autodoc_pages = generate_autodoc(app)
                if autodoc_pages:
                    autodoc_collection = DocsCollection(autodoc_pages)
                    holder.collection = holder.collection.merge(autodoc_collection)

        # -- MCP tools --
        if self._tools:
            from chirp.docs.tools import make_get_doc, make_list_docs, make_search_docs

            app.tool("search_docs", description="Search documentation by keyword")(
                make_search_docs(holder)
            )
            app.tool("get_doc", description="Retrieve a documentation page by slug")(
                make_get_doc(holder)
            )
            app.tool("list_docs", description="List documentation pages")(make_list_docs(holder))

        # -- Routes --

        use_suspense = self._suspense

        @app.route(f"{normalized_prefix}/")
        def docs_index():
            return Template(
                f"{_TEMPLATE_NS}/doc_list.html",
                docs_title=title,
                docs_nav_items=holder.collection.as_nav(),
                docs_prefix=normalized_prefix,
            )

        @app.route(f"{normalized_prefix}/search")
        def docs_search(request):
            q = (request.query.get("q") or "").strip()
            results = holder.collection.search(q) if q else ()
            return Fragment(
                f"{_TEMPLATE_NS}/doc_search_results.html",
                "doc_search_results",
                results=results,
                query=q,
                docs_prefix=normalized_prefix,
            )

        @app.route(f"{normalized_prefix}/{{slug:path}}")
        def docs_page(slug: str):
            doc = holder.collection.get(slug)
            if doc is None:
                from chirp.errors import NotFound

                raise NotFound()

            if use_suspense:

                async def _load_doc():
                    return doc

                return Suspense(
                    f"{_TEMPLATE_NS}/doc_page.html",
                    defer_blocks=("doc_content", "doc_toc"),
                    doc=_load_doc(),
                    docs_nav_items=holder.collection.as_nav(),
                    docs_prefix=normalized_prefix,
                )

            return Page(
                f"{_TEMPLATE_NS}/doc_page.html",
                "doc_content",
                doc=doc,
                docs_nav_items=holder.collection.as_nav(),
                docs_prefix=normalized_prefix,
            )

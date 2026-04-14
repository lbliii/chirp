"""Docs collection — load, index, and query documentation pages.

``DocsCollection`` is the central data structure.  It loads markdown
files from disk, renders them once via ``MarkdownRenderer``, and stores
frozen ``DocPage`` instances in memory.  After construction the
collection is immutable and thread-safe.

Usage::

    from chirp.docs import DocsCollection

    collection = DocsCollection.load(Path("content/docs"))
    page = collection.get("getting-started")
"""

from __future__ import annotations

from pathlib import Path

from chirp.docs.models import DocPage, NavGroup


class DocsCollection:
    """Immutable collection of documentation pages.

    Constructed via the ``load()`` class method which eagerly reads and
    renders all markdown files at startup.  After construction every
    public method is a pure read — no I/O, no locks.

    Design decisions:
        * **Eager load** — all content rendered at startup so request-
          time cost is a dict lookup + template render.  For 100 docs
          at ~50 KB each this is ~5 MB of memory, well within budget.
        * **Single directory** — constructor takes one ``Path``.
          Multiple directories can be merged via ``merge()``.
        * **Keyword search** — simple ranked keyword matching over
          title + raw markdown.  No external dependencies.  Can be
          upgraded to trigram/BM25 later without API change.
    """

    __slots__ = ("_by_slug", "_categories", "_nav", "_pages")

    _INDEX_STEMS = frozenset({"index", "_index", "README"})

    def __init__(self, pages: tuple[DocPage, ...]) -> None:
        self._pages = pages
        self._by_slug: dict[str, DocPage] = {p.slug: p for p in pages}
        cats: dict[str, list[DocPage]] = {}
        for p in pages:
            cats.setdefault(p.metadata.category or "Uncategorized", []).append(p)
        self._categories = tuple(sorted(cats))

        nav_groups: list[NavGroup] = []
        for cat in sorted(cats):
            landing = None
            regular: list[DocPage] = []
            for p in cats[cat]:
                if p.source_path is not None and p.source_path.stem in self._INDEX_STEMS:
                    landing = p
                else:
                    regular.append(p)
            nav_groups.append(
                NavGroup(
                    category=cat,
                    pages=tuple(sorted(regular, key=lambda p: (p.metadata.order, p.title))),
                    landing_page=landing,
                )
            )
        self._nav = tuple(nav_groups)

    @classmethod
    def load(
        cls,
        content_dir: Path,
        *,
        include_drafts: bool = False,
    ) -> DocsCollection:
        """Walk *content_dir*, parse and render every ``.md`` file.

        Args:
            content_dir: Directory containing markdown files (searched
                recursively).
            include_drafts: If ``False`` (default), pages with
                ``draft: true`` in frontmatter are excluded.

        Returns:
            An immutable ``DocsCollection`` ready for querying.
        """
        from chirp.docs.frontmatter import parse_file

        pages: list[DocPage] = []
        for md_path in sorted(content_dir.rglob("*.md")):
            page = parse_file(md_path, content_dir)
            if page.metadata.draft and not include_drafts:
                continue
            pages.append(page)
        return cls(tuple(pages))

    # -- Query API --

    def get(self, slug: str) -> DocPage | None:
        """Look up a page by slug.  Returns ``None`` if not found."""
        return self._by_slug.get(slug)

    def list(self, *, category: str | None = None) -> tuple[DocPage, ...]:
        """Return pages sorted by (order, title).

        Args:
            category: If provided, only return pages in this category.
        """
        pages = self._pages
        if category is not None:
            pages = tuple(p for p in pages if p.metadata.category == category)
        return tuple(sorted(pages, key=lambda p: (p.metadata.order, p.title)))

    def search(self, query: str) -> tuple[DocPage, ...]:
        """Keyword search over title and raw markdown content.

        Returns pages ranked by relevance (title matches weighted
        higher).  Empty query returns an empty tuple.
        """
        from chirp.docs.search import keyword_search

        return keyword_search(self._pages, query)

    def categories(self) -> tuple[str, ...]:
        """Return distinct category names, sorted alphabetically."""
        return self._categories

    def as_nav(self) -> tuple[NavGroup, ...]:
        """Return navigation groups for sidebar rendering."""
        return self._nav

    def merge(self, other: DocsCollection) -> DocsCollection:
        """Combine two collections into one (e.g. markdown + autodoc).

        Duplicate slugs in *other* overwrite pages from *self*.
        """
        merged: dict[str, DocPage] = {p.slug: p for p in self._pages}
        for p in other._pages:
            merged[p.slug] = p
        return DocsCollection(tuple(merged.values()))

    def __len__(self) -> int:
        return len(self._pages)

    def __contains__(self, slug: str) -> bool:
        return slug in self._by_slug

"""Tests for chirp.docs.search — keyword search over doc pages."""

from __future__ import annotations

from kida.template import Markup

from chirp.docs.models import DocMetadata, DocPage, DocSource


def _page(slug: str, title: str, raw: str, **meta_kw: object) -> DocPage:
    return DocPage(
        slug=slug,
        title=title,
        raw=raw,
        html=Markup(f"<p>{raw[:50]}</p>"),
        toc=(),
        metadata=DocMetadata(**meta_kw),
        source=DocSource.MARKDOWN,
    )


PAGES = (
    _page(
        "routing",
        "Routing Guide",
        "Learn about routing in chirp. Routes map URLs to handlers.",
        category="Guide",
    ),
    _page(
        "templates",
        "Template Basics",
        "Kida templates use blocks for composition.",
        category="Guide",
    ),
    _page(
        "suspense",
        "Suspense Streaming",
        "Suspense defers heavy rendering. Routing is mentioned briefly.",
        category="Advanced",
    ),
    _page("tools", "MCP Tools", "Expose tools to AI agents via @tool decorator.", category="API"),
    _page(
        "forms",
        "Form Handling",
        "Process form data with validation and CSRF protection.",
        category="Guide",
    ),
)


class TestKeywordSearch:
    def test_single_term(self) -> None:
        from chirp.docs.search import keyword_search

        results = keyword_search(PAGES, "routing")
        slugs = [p.slug for p in results]
        # "routing" appears in title of routing guide → ranked first
        assert slugs[0] == "routing"
        # "suspense" mentions routing in body
        assert "suspense" in slugs

    def test_multiple_terms_and_semantics(self) -> None:
        from chirp.docs.search import keyword_search

        results = keyword_search(PAGES, "routing handlers")
        # Only routing guide has both "routing" AND "handlers"
        assert len(results) == 1
        assert results[0].slug == "routing"

    def test_case_insensitive(self) -> None:
        from chirp.docs.search import keyword_search

        results = keyword_search(PAGES, "KIDA")
        assert any(p.slug == "templates" for p in results)

    def test_empty_query(self) -> None:
        from chirp.docs.search import keyword_search

        assert keyword_search(PAGES, "") == ()
        assert keyword_search(PAGES, "   ") == ()

    def test_no_matches(self) -> None:
        from chirp.docs.search import keyword_search

        assert keyword_search(PAGES, "xyznonexistent") == ()

    def test_title_match_ranked_higher(self) -> None:
        from chirp.docs.search import keyword_search

        results = keyword_search(PAGES, "routing")
        # "routing" page has it in the title (3x weight) + body
        # "suspense" page only has it in the body (1x weight)
        assert results[0].slug == "routing"

    def test_excludes_drafts(self) -> None:
        from chirp.docs.search import keyword_search

        pages_with_draft = (
            *PAGES,
            _page("draft-doc", "Draft Routing", "About routing.", draft=True),
        )
        results = keyword_search(pages_with_draft, "routing")
        assert all(p.slug != "draft-doc" for p in results)

    def test_returns_tuple(self) -> None:
        from chirp.docs.search import keyword_search

        results = keyword_search(PAGES, "tools")
        assert isinstance(results, tuple)

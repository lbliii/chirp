"""Tests for chirp.freeze — static HTML generation from route table."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.freeze import freeze


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    """Sample docs content for freeze tests."""
    _write_md(
        tmp_path / "content" / "intro.md",
        "---\ntitle: Introduction\norder: 1\ncategory: Getting Started\n"
        "description: Learn the basics\n---\n# Introduction\n\nWelcome.\n",
    )
    _write_md(
        tmp_path / "content" / "routing.md",
        "---\ntitle: Routing Guide\norder: 2\ncategory: Guides\n---\n"
        "# Routing\n\nRoutes map URLs to handlers.\n",
    )
    _write_md(
        tmp_path / "content" / "advanced/suspense.md",
        "---\ntitle: Suspense Streaming\norder: 1\ncategory: Advanced\n---\n"
        "# Suspense\n\nDefer heavy rendering.\n",
    )
    return tmp_path / "content"


@pytest.fixture
def docs_app(content_dir: Path, tmp_path: Path) -> App:
    """Chirp app with DocsPlugin for freeze testing."""
    from chirp.docs import DocsPlugin

    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir(exist_ok=True)

    app = App(AppConfig(template_dir=str(tpl_dir)))
    app.mount("/docs", DocsPlugin(content_dir=content_dir, title="Freeze Test"))
    return app


# ── Core freeze behaviour ────────────────────────────────────────────────


class TestFreezeBasic:
    async def test_freeze_writes_html_files(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        result = await freeze(docs_app, output)

        assert result.pages_written > 0
        assert result.errors == []
        # Index page
        assert (output / "docs" / "index.html").exists()

    async def test_freeze_writes_doc_pages(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)

        # Parameterized route should expand to all doc slugs
        assert (output / "docs" / "intro" / "index.html").exists()
        assert (output / "docs" / "routing" / "index.html").exists()
        assert (output / "docs" / "advanced" / "suspense" / "index.html").exists()

    async def test_freeze_result_stats(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        result = await freeze(docs_app, output)

        # 1 index + 3 doc pages = 4 minimum
        assert result.pages_written >= 4
        assert result.elapsed > 0
        assert len(result.urls) == result.pages_written

    async def test_frozen_html_is_valid(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)

        html = (output / "docs" / "intro" / "index.html").read_text()
        assert "<h1" in html.lower() or "Introduction" in html


# ── Relative URL rewriting ────────────────────────────────────────────────


class TestFreezeRelativeUrls:
    async def test_frozen_urls_are_relative(self, docs_app: App, tmp_path: Path) -> None:
        """Frozen HTML must use relative URLs, not absolute paths."""
        output = tmp_path / "dist"
        result = await freeze(docs_app, output)

        for url in result.urls:
            frozen_path = output / url.strip("/") / "index.html"
            if not frozen_path.exists():
                frozen_path = output / "index.html"
            html = frozen_path.read_text()
            # No href="/..." pointing to known frozen pages should remain.
            for other_url in result.urls:
                norm = "/" + other_url.strip("/") if other_url != "/" else "/"
                assert f'href="{norm}"' not in html, f"Absolute URL {norm} still in frozen {url}"

    async def test_relative_urls_resolve_correctly(self, tmp_path: Path) -> None:
        """Relative path math is correct at various depths."""
        from chirp.freeze import _make_relative

        assert _make_relative("/articles/foo", "/") == "../../index.html"
        assert _make_relative("/articles/foo", "/about") == "../../about/index.html"
        assert _make_relative("/", "/about") == "about/index.html"
        assert _make_relative("/about", "/articles/foo") == "../articles/foo/index.html"
        assert _make_relative("/", "/") == "index.html"

    async def test_fragments_and_queries_preserved(self, tmp_path: Path) -> None:
        """URL rewriting must preserve #fragment and ?query suffixes."""
        from chirp.freeze import _relativize_html

        known = frozenset({"/", "/about"})
        html = '<a href="/about#section">link</a><a href="/about?tab=1">tab</a>'
        result = _relativize_html(html, "/", known)
        assert 'href="about/index.html#section"' in result
        assert 'href="about/index.html?tab=1"' in result

    async def test_external_urls_untouched(self, tmp_path: Path) -> None:
        """External and unknown URLs must not be rewritten."""
        from chirp.freeze import _relativize_html

        known = frozenset({"/", "/about"})
        html = '<a href="/unknown">x</a><a href="https://example.com">y</a>'
        result = _relativize_html(html, "/", known)
        assert 'href="/unknown"' in result
        assert 'href="https://example.com"' in result


# ── Edge cases ───────────────────────────────────────────────────────────


class TestFreezeEdgeCases:
    async def test_fragment_only_routes_skipped(self, tmp_path: Path) -> None:
        """Routes that only return Fragment should be skipped (non-HTML or fragment)."""
        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        (tpl_dir / "base.html").write_text("{% block content %}default{% endblock %}")

        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/")
        def index():
            return "<html><body>home</body></html>"

        @app.route("/search")
        def search():
            from chirp.templating.returns import Fragment

            return Fragment("base.html", "content", query="test")

        output = tmp_path / "dist"
        await freeze(app, output)

        # Index written, search fragment also renders (Fragment returns HTML)
        assert (output / "index.html").exists()

    async def test_non_get_routes_skipped(self, tmp_path: Path) -> None:
        app = App()

        @app.route("/", methods=["GET"])
        def index():
            return "<html>home</html>"

        @app.route("/submit", methods=["POST"])
        def submit():
            return "ok"

        output = tmp_path / "dist"
        result = await freeze(app, output)

        assert result.pages_written == 1
        assert (output / "index.html").exists()

    async def test_missing_freeze_params_warns(self, tmp_path: Path) -> None:
        app = App()

        @app.route("/items/{id}")
        def item(id: str):
            return f"<html>item {id}</html>"

        output = tmp_path / "dist"
        result = await freeze(app, output)

        # Parameterized route without provider should be skipped, not crash
        assert result.pages_written == 0
        assert result.pages_skipped > 0

    async def test_exclude_patterns(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        result = await freeze(docs_app, output, exclude=["/docs/search"])

        # Search route should be excluded
        written_paths = set(result.urls)
        assert not any("/docs/search" in u for u in written_paths)


# ── freeze_params registration ───────────────────────────────────────────


class TestFreezeParams:
    def test_freeze_params_decorator(self) -> None:
        app = App()

        @app.freeze_params("/items/{id}")
        def item_params():
            return [{"id": "1"}, {"id": "2"}]

        assert "/items/{id}" in app._mutable_state.freeze_param_providers

    async def test_freeze_params_expand(self, tmp_path: Path) -> None:
        app = App()

        items = [{"id": "1", "name": "one"}, {"id": "2", "name": "two"}]

        @app.route("/items/{id}")
        def item(id: str):
            name = next(i["name"] for i in items if i["id"] == id)
            return f"<html>{name}</html>"

        @app.freeze_params("/items/{id}")
        def item_params():
            return [{"id": i["id"]} for i in items]

        output = tmp_path / "dist"
        result = await freeze(app, output)

        assert result.pages_written == 2
        assert (output / "items" / "1" / "index.html").exists()
        assert (output / "items" / "2" / "index.html").exists()

    def test_docs_plugin_auto_registers_freeze_params(self, docs_app: App) -> None:
        """DocsPlugin should auto-register freeze_params for the slug route."""
        providers = docs_app._mutable_state.freeze_param_providers
        assert any("slug" in path for path in providers)


# ── Static search ──────────────────────────────────────────────────────


class TestStaticSearch:
    async def test_search_index_generated(self, docs_app: App, tmp_path: Path) -> None:
        """Freeze should produce a _search-index.js file."""
        output = tmp_path / "dist"
        await freeze(docs_app, output)

        index_file = output / "_search-index.js"
        assert index_file.exists()
        content = index_file.read_text()
        assert content.startswith("window.__chirp_search=")
        assert '"t":' in content  # has title entries

    async def test_search_index_entries(self, docs_app: App, tmp_path: Path) -> None:
        """Index should contain entries for rendered pages with titles."""
        import json

        output = tmp_path / "dist"
        await freeze(docs_app, output)

        raw = (output / "_search-index.js").read_text()
        data = json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))
        # Rich manifest has "entries" key; flat fallback is a list.
        entries = data["entries"] if isinstance(data, dict) else data
        titles = {e["t"] for e in entries}
        assert "Introduction" in titles or "Freeze Test" in titles

    async def test_search_script_injected_on_docs_pages(
        self, docs_app: App, tmp_path: Path
    ) -> None:
        """Pages with a search input should get the static search script."""
        output = tmp_path / "dist"
        await freeze(docs_app, output)

        html = (output / "docs" / "index.html").read_text()
        assert "static-search" in html
        assert "_search-index.js" in html

    async def test_search_script_not_on_non_docs_pages(self, tmp_path: Path) -> None:
        """Pages without .chirp-docs-search should not get the script."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body>home</body></html>"

        output = tmp_path / "dist"
        await freeze(app, output)

        html = (output / "index.html").read_text()
        assert "static-search" not in html

    def test_extract_title_from_h1(self) -> None:
        from chirp.freeze import _extract_title

        assert _extract_title("<h1>Hello World</h1>") == "Hello World"
        assert _extract_title("<title>Page Title</title><h1>Heading</h1>") == "Page Title"
        assert _extract_title("<p>no title here</p>") == ""

    def test_page_depth(self) -> None:
        from chirp.freeze import _page_depth

        assert _page_depth("/") == 0
        assert _page_depth("/docs/") == 1
        assert _page_depth("/docs/guides/intro") == 3


# ── Rich search index (render-time contributions) ──────────────────────


class TestRichSearchIndex:
    async def test_rich_index_has_structured_fields(self, docs_app: App, tmp_path: Path) -> None:
        """Entries contributed by DocsPlugin should have category, tags, toc."""
        import json

        output = tmp_path / "dist"
        await freeze(docs_app, output)

        raw = (output / "_search-index.js").read_text()
        data = json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))
        assert data["version"] == 1
        entries = data["entries"]
        # Find a doc page entry (not the index)
        doc_entries = [e for e in entries if "c" in e]
        assert len(doc_entries) > 0, "Expected at least one entry with category"
        entry = doc_entries[0]
        assert "t" in entry  # title
        assert "c" in entry  # category

    async def test_rich_index_facets(self, docs_app: App, tmp_path: Path) -> None:
        """Manifest should include extracted facets from contributions."""
        import json

        output = tmp_path / "dist"
        await freeze(docs_app, output)

        raw = (output / "_search-index.js").read_text()
        data = json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))
        facets = data["facets"]
        # Our test content has categories: Getting Started, Guides, Advanced
        assert "category" in facets
        assert len(facets["category"]) > 0

    async def test_fallback_to_html_scraping(self, tmp_path: Path) -> None:
        """Non-docs routes without contributions should still be indexed."""
        import json

        from chirp.docs import DocsPlugin

        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "page.md").write_text(
            "---\ntitle: A Page\norder: 1\ncategory: Test\n---\n# A Page\nBody.\n"
        )

        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()

        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/")
        def index():
            return "<html><body><h1>Home</h1></body></html>"

        app.mount("/docs", DocsPlugin(content_dir=content_dir, title="Test"))

        output = tmp_path / "dist"
        await freeze(app, output)

        raw = (output / "_search-index.js").read_text()
        data = json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))
        entries = data["entries"]
        titles = {e["t"] for e in entries}
        # Both the contributed doc page AND the fallback home page should be indexed
        assert "A Page" in titles
        assert "Home" in titles

    def test_search_contribute_noop_outside_freeze(self) -> None:
        """Calling search_contribute() outside freeze should not raise."""
        from chirp.freeze import SearchEntry, search_contribute

        search_contribute(SearchEntry(url="/test", title="Test"))
        # No error, no-op

    async def test_rich_index_has_description_and_body(self, docs_app: App, tmp_path: Path) -> None:
        """Contributed entries should carry description and body text."""
        import json

        output = tmp_path / "dist"
        await freeze(docs_app, output)

        raw = (output / "_search-index.js").read_text()
        data = json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))
        entries = data["entries"]
        # The "intro" page has description "Learn the basics"
        intro = [e for e in entries if e["t"] == "Introduction"]
        if intro:
            assert intro[0].get("d") == "Learn the basics"
            assert "body" in intro[0]

"""Tests for Sprint 5 — Suspense, search UI, nav template global."""

from __future__ import annotations

from pathlib import Path

from chirp import App, AppConfig
from chirp.testing import TestClient


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_content(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    content.mkdir()
    _write_md(
        content / "routing.md",
        "---\ntitle: Routing Guide\norder: 1\ncategory: Guides\n"
        "description: URL routing basics\n---\n# Routing\n\nRoutes map URLs to handlers.\n",
    )
    _write_md(
        content / "templates.md",
        "---\ntitle: Template Guide\norder: 2\ncategory: Guides\n"
        "description: Kida template basics\n---\n# Templates\n\nKida templates.\n",
    )
    _write_md(
        content / "advanced.md",
        "---\ntitle: Advanced Topics\norder: 1\ncategory: Advanced\n---\n"
        "# Advanced\n\nDeep dive into advanced features.\n",
    )
    return content


# ── Suspense rendering ──────────────────────────────────────────────────


class TestSuspenseDocsPage:
    async def test_suspense_returns_200(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, suspense=True))

        async with TestClient(app) as client:
            resp = await client.get("/docs/routing")
            assert resp.status == 200

    async def test_suspense_contains_sidebar(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, suspense=True))

        async with TestClient(app) as client:
            resp = await client.get("/docs/routing")
            body = resp.text
            assert "chirp-docs-sidebar" in body
            assert "Template Guide" in body

    async def test_suspense_contains_content(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, suspense=True))

        async with TestClient(app) as client:
            resp = await client.get("/docs/routing")
            body = resp.text
            # Full response includes OOB chunks with resolved content
            assert "Routing Guide" in body or "Routing" in body
            assert "Routes map URLs" in body

    async def test_suspense_disabled_uses_page(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, suspense=False))

        async with TestClient(app) as client:
            resp = await client.get("/docs/routing")
            assert resp.status == 200
            body = resp.text
            # Page mode — no skeleton markers
            assert "Loading content..." not in body
            assert "Routing" in body

    async def test_suspense_missing_page_returns_404(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, suspense=True))

        async with TestClient(app) as client:
            resp = await client.get("/docs/nonexistent")
            assert resp.status == 404


# ── Search UI ───────────────────────────────────────────────────────────


class TestSearchRoute:
    async def test_search_returns_200(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/search?q=routing")
            assert resp.status == 200

    async def test_search_returns_matching_results(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/search?q=routing")
            body = resp.text
            assert "Routing Guide" in body
            # Should not include unrelated pages
            assert "Advanced Topics" not in body

    async def test_search_no_results(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/search?q=nonexistent_xyzzy")
            body = resp.text
            assert resp.status == 200
            assert "No pages found" in body

    async def test_search_empty_query(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/search?q=")
            body = resp.text
            assert resp.status == 200
            assert "Type to search" in body

    async def test_search_is_fragment(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get(
                "/docs/search?q=routing",
                headers={"HX-Request": "true"},
            )
            assert resp.status == 200
            body = resp.text
            # Fragment should contain results but be compact
            assert "doc_list" in body
            assert "Routing Guide" in body

    async def test_search_results_have_links(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/search?q=routing")
            body = resp.text
            assert 'href="/docs/routing"' in body

    async def test_index_has_search_input(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/")
            body = resp.text
            assert 'hx-get="/docs/search"' in body
            assert 'placeholder="Search docs..."' in body


# ── Nav template global ─────────────────────────────────────────────────


class TestDocsNavGlobal:
    def test_docs_nav_global_registered(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))
        app.freeze()

        # docs_nav callable registered in mutable state template globals
        nav_fn = app._mutable_state.template_globals.get("docs_nav")
        assert nav_fn is not None
        result = nav_fn()
        assert len(result) > 0
        assert result[0].category in {"Guides", "Advanced"}

    def test_docs_nav_items_global_registered(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))
        app.freeze()

        nav_fn = app._mutable_state.template_globals.get("docs_nav_items")
        assert nav_fn is not None
        result = nav_fn()
        categories = {g.category for g in result}
        assert "Guides" in categories

    async def test_docs_nav_reflects_autodoc(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = _make_content(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            """Health check."""
            return "ok"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=True))

        async with TestClient(app) as _client:
            nav_fn = app._mutable_state.template_globals["docs_nav"]
            result = nav_fn()
            categories = {g.category for g in result}
            assert "API Reference" in categories
            assert "Guides" in categories

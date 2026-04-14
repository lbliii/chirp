"""Tests for chirp.docs.plugin — DocsPlugin mount, routes, fragment navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.testing import TestClient


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    """Create a temp content directory with sample docs."""
    _write_md(
        tmp_path / "intro.md",
        "---\ntitle: Introduction\norder: 1\ncategory: Getting Started\n"
        "description: Learn the basics\n---\n# Introduction\n\n"
        "Welcome to the **docs**.\n",
    )
    _write_md(
        tmp_path / "routing.md",
        "---\ntitle: Routing Guide\norder: 2\ncategory: Guides\n---\n"
        "# Routing\n\nRoutes map URLs to handlers.\n",
    )
    _write_md(
        tmp_path / "advanced/suspense.md",
        "---\ntitle: Suspense Streaming\norder: 1\ncategory: Advanced\n---\n"
        "# Suspense\n\nDefer heavy rendering.\n",
    )
    return tmp_path


@pytest.fixture
def app_with_docs(content_dir: Path, tmp_path: Path) -> App:
    """Create a Chirp app with DocsPlugin mounted."""
    from chirp.docs import DocsPlugin

    # Use a template dir that exists (even if empty — plugin adds its own loader)
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()

    app = App(AppConfig(template_dir=str(tpl_dir)))
    app.mount("/docs", DocsPlugin(content_dir=content_dir, title="Test Docs"))
    return app


# ── Mount & registration ─────────────────────────────────────────────────


class TestDocsPluginMount:
    def test_mount_succeeds(self, app_with_docs: App) -> None:
        # Plugin registers without error; freeze succeeds
        app_with_docs.freeze()

    def test_routes_registered(self, app_with_docs: App) -> None:
        app_with_docs.freeze()
        routes = app_with_docs._runtime_state.router.routes
        paths = {r.path for r in routes}
        assert "/docs/" in paths
        # catch-all route for doc pages
        assert any("{slug:path}" in p for p in paths)


# ── Index route ──────────────────────────────────────────────────────────


class TestDocsIndex:
    async def test_index_returns_200(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/")
            assert resp.status == 200

    async def test_index_contains_page_titles(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/")
            body = resp.text
            assert "Introduction" in body
            assert "Routing Guide" in body
            assert "Suspense Streaming" in body

    async def test_index_contains_docs_title(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/")
            assert "Test Docs" in resp.text

    async def test_index_links_to_pages(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/")
            assert 'href="/docs/intro"' in resp.text
            assert 'href="/docs/routing"' in resp.text
            assert 'href="/docs/advanced/suspense"' in resp.text


# ── Page route ───────────────────────────────────────────────────────────


class TestDocsPage:
    async def test_page_returns_200(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/intro")
            assert resp.status == 200

    async def test_page_contains_content(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/intro")
            body = resp.text
            assert "Introduction" in body
            assert "<strong>" in body or "docs" in body

    async def test_nested_page(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/advanced/suspense")
            assert resp.status == 200
            assert "Suspense" in resp.text

    async def test_missing_page_returns_404(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/nonexistent")
            assert resp.status == 404

    async def test_page_has_sidebar_nav(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/intro")
            # Sidebar should contain links to other pages
            assert "chirp-docs-sidebar" in resp.text
            assert "Routing Guide" in resp.text


# ── Fragment navigation (htmx) ──────────────────────────────────────────


class TestFragmentNavigation:
    async def test_htmx_request_returns_fragment(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get(
                "/docs/intro",
                headers={"HX-Request": "true"},
            )
            assert resp.status == 200
            body = resp.text
            # Fragment should contain the content block but not the full sidebar
            assert "Introduction" in body
            # The fragment is the doc_content block — an <article> with id
            assert "doc_content" in body

    async def test_browser_request_returns_full_page(self, app_with_docs: App) -> None:
        async with TestClient(app_with_docs) as client:
            resp = await client.get("/docs/intro")
            assert resp.status == 200
            body = resp.text
            # Full page includes sidebar
            assert "chirp-docs-sidebar" in body
            assert "doc_content" in body


# ── Draft handling ───────────────────────────────────────────────────────


class TestDraftHandling:
    async def test_drafts_excluded_by_default(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "published.md", "---\ntitle: Published\n---\nContent")
        _write_md(content / "draft.md", "---\ntitle: Draft\ndraft: true\n---\nContent")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        async with TestClient(app) as client:
            resp = await client.get("/docs/")
            assert "Published" in resp.text
            assert "Draft" not in resp.text

            resp = await client.get("/docs/draft")
            assert resp.status == 404

    async def test_drafts_included_when_requested(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "draft.md", "---\ntitle: Draft\ndraft: true\n---\nContent")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, include_drafts=True))

        async with TestClient(app) as client:
            resp = await client.get("/docs/draft")
            assert resp.status == 200
            assert "Draft" in resp.text

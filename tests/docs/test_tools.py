"""Tests for chirp.docs.tools — MCP tool functions for AI agent access."""

from __future__ import annotations

from pathlib import Path

from chirp import App, AppConfig
from chirp.testing import TestClient


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Tool function unit tests ────────────────────────────────────────────


class TestSearchDocs:
    def test_returns_matching_pages(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_search_docs

        content = tmp_path / "content"
        content.mkdir()
        _write_md(
            content / "routing.md", "---\ntitle: Routing\n---\n# Routing\n\nURL routing guide."
        )
        _write_md(
            content / "templates.md", "---\ntitle: Templates\n---\n# Templates\n\nKida templates."
        )

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        search = make_search_docs(holder)

        results = search("routing")
        assert len(results) >= 1
        assert results[0]["slug"] == "routing"
        assert results[0]["title"] == "Routing"
        assert results[0]["source"] == "markdown"
        assert "content" in results[0]

    def test_returns_empty_for_no_match(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_search_docs

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide\n\nA guide.")

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        search = make_search_docs(holder)

        results = search("nonexistent_xyzzy")
        assert results == []


class TestGetDoc:
    def test_returns_page_by_slug(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_get_doc

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "intro.md", "---\ntitle: Introduction\n---\n# Intro\n\nWelcome.")

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        get_doc = make_get_doc(holder)

        result = get_doc("intro")
        assert result["slug"] == "intro"
        assert result["title"] == "Introduction"
        assert "Welcome" in result["content"]
        assert result["source"] == "markdown"

    def test_returns_error_for_missing_slug(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_get_doc

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide")

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        get_doc = make_get_doc(holder)

        result = get_doc("nonexistent")
        assert "error" in result


class TestListDocs:
    def test_lists_all_pages(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_list_docs

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "a.md", "---\ntitle: Alpha\ncategory: Guide\n---\n# Alpha")
        _write_md(content / "b.md", "---\ntitle: Beta\ncategory: Reference\n---\n# Beta")

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        list_docs = make_list_docs(holder)

        results = list_docs()
        assert len(results) == 2
        slugs = {r["slug"] for r in results}
        assert "a" in slugs
        assert "b" in slugs
        # list_docs omits content for brevity
        assert "content" not in results[0]

    def test_filters_by_category(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection
        from chirp.docs.plugin import _CollectionHolder
        from chirp.docs.tools import make_list_docs

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "a.md", "---\ntitle: Alpha\ncategory: Guide\n---\n# Alpha")
        _write_md(content / "b.md", "---\ntitle: Beta\ncategory: Reference\n---\n# Beta")

        collection = DocsCollection.load(content)
        holder = _CollectionHolder(collection)
        list_docs = make_list_docs(holder)

        results = list_docs(category="Guide")
        assert len(results) == 1
        assert results[0]["slug"] == "a"


# ── Plugin integration: tools registered on app ─────────────────────────


class TestToolsRegisteredOnApp:
    def test_tools_registered_when_enabled(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide\n\nA guide.")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=True))
        app.freeze()

        registry = app._runtime_state.tool_registry
        tool_names = {t["name"] for t in registry.list_tools()}
        assert "search_docs" in tool_names
        assert "get_doc" in tool_names
        assert "list_docs" in tool_names

    def test_tools_not_registered_when_disabled(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=False))
        app.freeze()

        registry = app._runtime_state.tool_registry
        tool_names = {t["name"] for t in registry.list_tools()}
        assert "search_docs" not in tool_names
        assert "get_doc" not in tool_names
        assert "list_docs" not in tool_names


# ── MCP endpoint integration ────────────────────────────────────────────


class TestMcpEndpoint:
    async def test_tools_list_includes_doc_tools(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide\n\nA guide.")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert resp.status == 200
            data = resp.json
            tool_names = {t["name"] for t in data["result"]["tools"]}
            assert "search_docs" in tool_names
            assert "get_doc" in tool_names
            assert "list_docs" in tool_names

    async def test_call_search_docs_via_mcp(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "routing.md", "---\ntitle: Routing\n---\n# Routing\n\nURL routing.")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "search_docs", "arguments": {"query": "routing"}},
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "routing" in result.lower()

    async def test_call_get_doc_via_mcp(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "intro.md", "---\ntitle: Intro\n---\n# Intro\n\nWelcome.")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "get_doc", "arguments": {"slug": "intro"}},
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "Welcome" in result

    async def test_call_list_docs_via_mcp(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "a.md", "---\ntitle: Alpha\n---\n# Alpha")
        _write_md(content / "b.md", "---\ntitle: Beta\n---\n# Beta")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "list_docs", "arguments": {}},
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "Alpha" in result
            assert "Beta" in result


# ── Tools see autodoc pages after startup ────────────────────────────────


class TestToolsWithAutodoc:
    async def test_search_finds_autodoc_pages(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide\n\nA guide.")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            """Health check endpoint."""
            return "ok"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=True, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "search_docs", "arguments": {"query": "health"}},
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "health" in result.lower()

    async def test_get_doc_retrieves_autodoc_page(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "guide.md", "---\ntitle: Guide\n---\n# Guide")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            """Health check endpoint."""
            return "ok"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=True, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "get_doc",
                        "arguments": {"slug": "api/routes/api-health"},
                    },
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "health" in result.lower()

    async def test_list_docs_includes_autodoc_category(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(
            content / "guide.md",
            "---\ntitle: Guide\ncategory: Guides\n---\n# Guide",
        )

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            """Health check."""
            return "ok"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=True, tools=True))

        async with TestClient(app) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "list_docs",
                        "arguments": {"category": "API Reference"},
                    },
                },
            )
            assert resp.status == 200
            data = resp.json
            result = data["result"]["content"][0]["text"]
            assert "api/routes" in result or "health" in result.lower()

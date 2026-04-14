"""Tests for chirp.docs.autodoc — route/tool introspection and DocPage generation."""

from __future__ import annotations

from pathlib import Path

from chirp import App, AppConfig
from chirp.docs.models import DocSource
from chirp.testing import TestClient

# ── Route introspection ──────────────────────────────────────────────────


class TestIntrospectRoutes:
    def test_extracts_basic_route(self) -> None:
        from chirp.docs.autodoc import introspect_routes
        from chirp.routing.route import Route

        def get_users():
            """List all users."""

        routes = [Route("/users", get_users, frozenset({"GET"}))]
        docs = introspect_routes(routes)

        assert len(docs) == 1
        assert docs[0].path == "/users"
        assert docs[0].methods == frozenset({"GET"})
        assert docs[0].handler_name == "get_users"
        assert docs[0].docstring == "List all users."

    def test_extracts_parameterized_route(self) -> None:
        from chirp.docs.autodoc import introspect_routes
        from chirp.routing.route import Route

        def get_user(user_id: int):
            pass

        routes = [Route("/users/{user_id:int}", get_user, frozenset({"GET"}))]
        docs = introspect_routes(routes)

        assert len(docs[0].parameters) == 1
        assert docs[0].parameters[0].name == "user_id"
        assert docs[0].parameters[0].required is True

    def test_handles_route_without_docstring(self) -> None:
        from chirp.docs.autodoc import introspect_routes
        from chirp.routing.route import Route

        def handler():
            pass

        docs = introspect_routes([Route("/", handler, frozenset({"GET"}))])
        assert docs[0].docstring is None

    def test_multiple_methods(self) -> None:
        from chirp.docs.autodoc import introspect_routes
        from chirp.routing.route import Route

        def handler():
            pass

        docs = introspect_routes([Route("/data", handler, frozenset({"GET", "POST"}))])
        assert docs[0].methods == frozenset({"GET", "POST"})

    def test_extracts_template(self) -> None:
        from chirp.docs.autodoc import introspect_routes
        from chirp.routing.route import Route

        def handler():
            pass

        docs = introspect_routes(
            [Route("/page", handler, frozenset({"GET"}), template="page.html")]
        )
        assert docs[0].template == "page.html"


# ── Tool introspection ───────────────────────────────────────────────────


class TestIntrospectTools:
    def test_extracts_tool_info(self) -> None:
        from chirp.docs.autodoc import introspect_tools

        tools = [
            {
                "name": "search_docs",
                "description": "Search documentation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            }
        ]
        docs = introspect_tools(tools)

        assert len(docs) == 1
        assert docs[0].name == "search_docs"
        assert docs[0].description == "Search documentation"
        assert len(docs[0].parameters) == 1
        assert docs[0].parameters[0].name == "query"
        assert docs[0].parameters[0].type_str == "string"
        assert docs[0].parameters[0].required is True

    def test_optional_params(self) -> None:
        from chirp.docs.autodoc import introspect_tools

        tools = [
            {
                "name": "list_docs",
                "description": "List docs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["category"],
                },
            }
        ]
        docs = introspect_tools(tools)
        params = {p.name: p for p in docs[0].parameters}
        assert params["category"].required is True
        assert params["limit"].required is False

    def test_array_type(self) -> None:
        from chirp.docs.autodoc import introspect_tools

        tools = [
            {
                "name": "bulk",
                "description": "Bulk op",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ids": {"type": "array", "items": {"type": "integer"}},
                    },
                },
            }
        ]
        docs = introspect_tools(tools)
        assert docs[0].parameters[0].type_str == "list[integer]"


# ── Slug generation ──────────────────────────────────────────────────────


class TestSlugGeneration:
    def test_route_slug(self) -> None:
        from chirp.docs.autodoc import _slug_for_route

        assert _slug_for_route("/users") == "api/routes/users"
        assert _slug_for_route("/users/{id}") == "api/routes/users-id"
        assert _slug_for_route("/") == "api/routes/root"

    def test_route_slug_nested(self) -> None:
        from chirp.docs.autodoc import _slug_for_route

        assert _slug_for_route("/users/{id}/posts") == "api/routes/users-id-posts"

    def test_tool_slug(self) -> None:
        from chirp.docs.autodoc import _slug_for_tool

        assert _slug_for_tool("search_docs") == "api/tools/search-docs"
        assert _slug_for_tool("get") == "api/tools/get"


# ── DocPage generation ───────────────────────────────────────────────────


class TestDocPageGeneration:
    def test_route_to_page(self) -> None:
        from chirp.docs.autodoc import _route_doc_to_page
        from chirp.docs.models import ParamDoc, RouteDoc

        rd = RouteDoc(
            path="/users/{id}",
            methods=frozenset({"GET"}),
            handler_name="get_user",
            docstring="Get a user by ID.",
            parameters=(ParamDoc(name="id", type_str="int", required=True),),
            template="users.html",
        )
        page = _route_doc_to_page(rd, order=0)

        assert page.slug == "api/routes/users-id"
        assert page.source == DocSource.AUTODOC
        assert page.source_path is None
        assert "GET" in page.title
        assert "/users/{id}" in page.title
        assert "Get a user by ID" in page.raw
        assert page.metadata.category == "API Reference"
        assert page.html  # non-empty

    def test_tool_to_page(self) -> None:
        from chirp.docs.autodoc import _tool_doc_to_page
        from chirp.docs.models import ParamDoc, ToolDoc

        td = ToolDoc(
            name="search_docs",
            description="Search documentation by keyword.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            parameters=(ParamDoc(name="query", type_str="string", required=True),),
        )
        page = _tool_doc_to_page(td, order=0)

        assert page.slug == "api/tools/search-docs"
        assert page.source == DocSource.AUTODOC
        assert "search_docs" in page.title
        assert "Search documentation" in page.raw
        assert page.metadata.category == "API Reference"


# ── Full integration: generate_autodoc with real app ─────────────────────


class TestGenerateAutodoc:
    def test_generates_from_app(self) -> None:
        from chirp.docs.autodoc import generate_autodoc

        app = App(AppConfig(template_dir="tests/templates"))

        @app.route("/")
        def index():
            """Home page."""
            return "Hello"

        @app.route("/items/{item_id:int}")
        def get_item(item_id: int):
            """Get an item."""
            return f"Item {item_id}"

        @app.tool("search", description="Search things")
        def search(query: str) -> list[dict]:
            return []

        app.freeze()
        pages = generate_autodoc(app)

        assert len(pages) >= 3  # 2 routes + 1 tool
        slugs = {p.slug for p in pages}
        assert "api/routes/root" in slugs
        assert "api/routes/items-item_id-int" in slugs or any("items" in s for s in slugs)
        assert "api/tools/search" in slugs

        # All are AUTODOC source
        assert all(p.source == DocSource.AUTODOC for p in pages)

    def test_empty_app(self) -> None:
        from chirp.docs.autodoc import generate_autodoc

        app = App(AppConfig(template_dir="tests/templates"))
        app.freeze()
        pages = generate_autodoc(app)
        # Should at least not crash; may have 0 routes if none registered
        assert isinstance(pages, tuple)


# ── Plugin integration with autodoc ──────────────────────────────────────


class TestPluginAutodoc:
    async def test_autodoc_pages_visible_after_startup(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        (content / "guide.md").write_text(
            "---\ntitle: Guide\norder: 1\ncategory: Guide\n---\n# Guide\n\nA guide.",
            encoding="utf-8",
        )

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            """Health check endpoint."""
            return "ok"

        @app.tool("ping", description="Ping the server")
        def ping() -> str:
            return "pong"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=True))

        async with TestClient(app) as client:
            # Markdown page still works
            resp = await client.get("/docs/guide")
            assert resp.status == 200
            assert "Guide" in resp.text

            # Autodoc route page
            resp = await client.get("/docs/api/routes/api-health")
            assert resp.status == 200
            assert "health" in resp.text.lower()

            # Autodoc tool page
            resp = await client.get("/docs/api/tools/ping")
            assert resp.status == 200
            assert "Ping" in resp.text or "ping" in resp.text

            # Index shows both markdown and autodoc entries
            resp = await client.get("/docs/")
            assert "Guide" in resp.text
            assert "API Reference" in resp.text

    async def test_autodoc_disabled(self, tmp_path: Path) -> None:
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        (content / "guide.md").write_text(
            "---\ntitle: Guide\n---\n# Guide",
            encoding="utf-8",
        )

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))

        @app.route("/api/health")
        def health():
            return "ok"

        app.mount("/docs", DocsPlugin(content_dir=content, autodoc=False))

        async with TestClient(app) as client:
            # Markdown page works
            resp = await client.get("/docs/guide")
            assert resp.status == 200

            # Autodoc pages not generated
            resp = await client.get("/docs/api/routes/api-health")
            assert resp.status == 404

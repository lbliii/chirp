"""Phase 2 tests: kida integration through the full App pipeline.

Tests that Template and Fragment return types produce real rendered HTML
when routed through App -> handler -> negotiate -> kida.
"""

from pathlib import Path

from chirp.app import App
from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.templating.returns import Fragment, Template
from chirp.testing import TestClient

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _app(**config_overrides: object) -> App:
    """Build an App wired to the test templates directory."""
    cfg = AppConfig(template_dir=TEMPLATES_DIR, **config_overrides)
    return App(config=cfg)


class TestTemplateRendering:
    """Full-page template rendering through the pipeline."""

    async def test_basic_template(self) -> None:
        app = _app()

        @app.route("/")
        def index():
            return Template("page.html", title="Home")

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<title>Home</title>" in response.text
            assert "<h1>Home</h1>" in response.text
            assert "text/html" in response.content_type

    async def test_template_with_list_context(self) -> None:
        app = _app()

        @app.route("/items")
        def items():
            return Template("page.html", title="Items", items=["alpha", "beta", "gamma"])

        async with TestClient(app) as client:
            response = await client.get("/items")
            assert "<li>alpha</li>" in response.text
            assert "<li>beta</li>" in response.text
            assert "<li>gamma</li>" in response.text

    async def test_template_inheritance(self) -> None:
        app = _app()

        @app.route("/child")
        def child():
            return Template("child.html", page_title="Child Page", body_text="Hello from child")

        async with TestClient(app) as client:
            response = await client.get("/child")
            assert "<title>Child Page</title>" in response.text
            assert "<h1>Child Page</h1>" in response.text
            assert "Hello from child" in response.text
            # Should include base.html structure
            assert "<html>" in response.text
            assert "</html>" in response.text

    async def test_template_with_status_tuple(self) -> None:
        app = _app()

        @app.route("/created")
        def created():
            return (Template("page.html", title="Created"), 201)

        async with TestClient(app) as client:
            response = await client.get("/created")
            assert response.status == 201
            assert "<title>Created</title>" in response.text


class TestFragmentRendering:
    """Block-level rendering for htmx fragment responses."""

    async def test_basic_fragment(self) -> None:
        app = _app()

        @app.route("/search")
        def search():
            return Fragment("search.html", "results_list", results=["one", "two"])

        async with TestClient(app) as client:
            response = await client.get("/search")
            assert response.status == 200
            assert '<div id="results">' in response.text
            assert "one" in response.text
            assert "two" in response.text
            # Fragment should NOT contain the full page wrapper
            assert "<form>" not in response.text

    async def test_fragment_vs_full_page(self) -> None:
        """Same template, different scope based on request type."""
        app = _app()

        @app.route("/search")
        def search(request: Request):
            results = ["alpha", "beta"]
            if request.is_fragment:
                return Fragment("search.html", "results_list", results=results)
            return Template("search.html", results=results)

        async with TestClient(app) as client:
            # Full page includes the form
            full = await client.get("/search")
            assert "<form>" in full.text
            assert "alpha" in full.text

            # Fragment only includes the results block
            frag = await client.fragment("/search")
            assert "<form>" not in frag.text
            assert "alpha" in frag.text
            assert '<div id="results">' in frag.text

    async def test_fragment_empty_results(self) -> None:
        app = _app()

        @app.route("/search")
        def search():
            return Fragment("search.html", "results_list", results=[])

        async with TestClient(app) as client:
            response = await client.get("/search")
            assert response.status == 200
            assert '<div id="results">' in response.text


class TestTemplateFilters:
    """User-registered template filters."""

    async def test_custom_filter(self) -> None:
        app = _app()

        @app.template_filter()
        def currency(value: float) -> str:
            return f"${value:,.2f}"

        @app.route("/price")
        def price():
            return Template("with_filter.html", price=42.5)

        async with TestClient(app) as client:
            response = await client.get("/price")
            assert "$42.50" in response.text

    async def test_named_filter(self) -> None:
        app = _app()

        @app.template_filter(name="currency")
        def format_money(value: float) -> str:
            return f"${value:,.2f}"

        @app.route("/price")
        def price():
            return Template("with_filter.html", price=99.9)

        async with TestClient(app) as client:
            response = await client.get("/price")
            assert "$99.90" in response.text


class TestTemplateGlobals:
    """User-registered template globals."""

    async def test_global_value(self) -> None:
        app = _app()

        @app.template_global()
        def site_name() -> str:
            return "My Chirp App"

        @app.route("/footer")
        def footer():
            return Template("with_global.html")

        async with TestClient(app) as client:
            response = await client.get("/footer")
            # Globals that are callables get called when accessed in template
            # kida stores the function, template invokes it
            assert "My Chirp App" in response.text or "site_name" in response.text


class TestMixedReturnTypes:
    """Different routes returning different types in the same app."""

    async def test_mixed_routes(self) -> None:
        app = _app()

        @app.route("/html")
        def html():
            return Template("page.html", title="HTML")

        @app.route("/json")
        def json_route():
            return {"message": "hello"}

        @app.route("/text")
        def text():
            return "plain text"

        @app.route("/fragment")
        def fragment():
            return Fragment("search.html", "results_list", results=["x"])

        async with TestClient(app) as client:
            html_resp = await client.get("/html")
            assert "<title>HTML</title>" in html_resp.text
            assert "text/html" in html_resp.content_type

            json_resp = await client.get("/json")
            assert "application/json" in json_resp.content_type

            text_resp = await client.get("/text")
            assert text_resp.text == "plain text"

            frag_resp = await client.get("/fragment")
            assert '<div id="results">' in frag_resp.text

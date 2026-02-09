"""Tests for HTML injection middleware."""

from chirp.app import App
from chirp.middleware.inject import HTMLInject
from chirp.testing import TestClient


SCRIPT_TAG = '<script src="/__reload.js"></script>'


class TestHTMLInjectBasic:
    async def test_injects_before_closing_body(self) -> None:
        """Snippet is inserted before </body>."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert SCRIPT_TAG + "</body>" in response.text

    async def test_appends_when_no_target(self) -> None:
        """When </body> is absent, snippet is appended to the end."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/")
        def index():
            return "<h1>Fragment</h1>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.text.endswith(SCRIPT_TAG)

    async def test_custom_before_target(self) -> None:
        """The 'before' parameter controls the injection point."""
        app = App()
        app.add_middleware(HTMLInject("<!-- injected -->", before="</head>"))

        @app.route("/")
        def index():
            return "<html><head><title>T</title></head><body></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert "<!-- injected --></head>" in response.text

    async def test_only_first_occurrence_replaced(self) -> None:
        """If the target appears multiple times, only the first is injected."""
        app = App()
        app.add_middleware(HTMLInject("X", before="Z"))

        @app.route("/")
        def index():
            return "aZbZc"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.text == "aXZbZc"


class TestHTMLInjectSkips:
    async def test_skips_non_html_response(self) -> None:
        """CSS, JSON, etc. are not modified."""
        from chirp.http.response import Response as Resp

        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/style.css")
        def css():
            return Resp(body="body { color: red; }</body>", content_type="text/css")

        async with TestClient(app) as client:
            response = await client.get("/style.css")
            assert SCRIPT_TAG not in response.text
            assert "body { color: red; }</body>" in response.text

    async def test_skips_json_response(self) -> None:
        """JSON responses are not modified."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/api")
        def api():
            return {"key": "value</body>"}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert SCRIPT_TAG not in response.text

    async def test_skips_sse_response(self) -> None:
        """SSE (EventStream) responses are passed through unchanged."""
        from chirp import EventStream, SSEEvent

        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/events")
        def events():
            async def stream():
                yield SSEEvent(data="</body>", event="test")

            return EventStream(stream())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1, disconnect_after=2.0)
            assert result.status == 200
            assert len(result.events) == 1
            # The </body> data should NOT have been modified by HTMLInject
            assert result.events[0].data == "</body>"

    async def test_handles_html_with_charset(self) -> None:
        """Injection works when content_type includes charset."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/")
        def index():
            return "<html><body>Hi</body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            # chirp sets text/html; charset=utf-8 by default
            assert "text/html" in response.content_type
            assert SCRIPT_TAG + "</body>" in response.text


class TestHTMLInjectWithStaticFiles:
    async def test_injects_into_static_html(self, tmp_path) -> None:
        """HTMLInject works together with StaticFiles."""
        from chirp.middleware.static import StaticFiles

        site = tmp_path / "public"
        site.mkdir()
        (site / "index.html").write_text(
            "<html><body><p>Hello</p></body></html>"
        )

        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))
        app.add_middleware(StaticFiles(directory=site, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert SCRIPT_TAG + "</body>" in response.text
            assert "<p>Hello</p>" in response.text

    async def test_does_not_inject_into_static_css(self, tmp_path) -> None:
        """HTMLInject does not touch CSS files from StaticFiles."""
        from chirp.middleware.static import StaticFiles

        site = tmp_path / "public"
        site.mkdir()
        (site / "style.css").write_text("body { color: red; }")

        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))
        app.add_middleware(StaticFiles(directory=site, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/style.css")
            assert response.status == 200
            assert SCRIPT_TAG not in response.text


class TestHTMLInjectExport:
    def test_importable_from_middleware_package(self) -> None:
        """HTMLInject is importable from chirp.middleware."""
        from chirp.middleware import HTMLInject as Imported

        assert Imported is HTMLInject

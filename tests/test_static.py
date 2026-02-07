"""Tests for static file serving middleware."""

import pytest

from chirp.app import App
from chirp.middleware.static import StaticFiles
from chirp.testing import TestClient


@pytest.fixture
def static_dir(tmp_path):
    """Create temporary static files for testing."""
    static = tmp_path / "static"
    static.mkdir()

    # Create test files
    (static / "style.css").write_text("body { color: red; }")
    (static / "app.js").write_text("console.log('hello');")
    (static / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (static / "data.bin").write_bytes(b"\x00\x01\x02\x03")

    # Nested directory
    sub = static / "css"
    sub.mkdir()
    (sub / "main.css").write_text("h1 { font-size: 2em; }")

    return static


class TestStaticFileServing:
    async def test_serves_css_file(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            assert response.status == 200
            assert "text/css" in response.content_type
            assert "body { color: red; }" in response.text

    async def test_serves_js_file(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/app.js")
            assert response.status == 200
            assert "console.log" in response.text

    async def test_serves_binary_file(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/image.png")
            assert response.status == 200
            assert "image/png" in response.content_type

    async def test_serves_nested_file(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/css/main.css")
            assert response.status == 200
            assert "h1 { font-size: 2em; }" in response.text

    async def test_unknown_extension_gets_octet_stream(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/data.bin")
            assert response.status == 200
            assert response.content_type == "application/octet-stream"


class TestStaticFileFallthrough:
    async def test_nonexistent_file_falls_through(self, static_dir) -> None:
        """Missing file should fall through to the next handler (router)."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/nonexistent.css")
            assert response.status == 404

    async def test_non_matching_prefix_falls_through(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/assets"))

        @app.route("/api/data")
        def data():
            return "api"

        async with TestClient(app) as client:
            response = await client.get("/api/data")
            assert response.status == 200
            assert response.text == "api"

    async def test_post_request_falls_through(self, static_dir) -> None:
        """Static files only serve GET and HEAD."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/static/style.css", methods=["POST"])
        def upload():
            return ("uploaded", 201)

        async with TestClient(app) as client:
            response = await client.post("/static/style.css")
            assert response.status == 201


class TestStaticFilePathTraversal:
    async def test_path_traversal_blocked(self, static_dir) -> None:
        """Path traversal attempts should return 403."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/../../../etc/passwd")
            # Either 403 (traversal caught) or 404 (file not found after resolution)
            assert response.status in (403, 404)


class TestStaticFileCaching:
    async def test_cache_control_header(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            assert any(name == "cache-control" for name, _ in response.headers)

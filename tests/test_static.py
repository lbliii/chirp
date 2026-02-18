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
    (static / "index.html").write_text("<h1>Home</h1>")
    (static / "404.html").write_text("<h1>Not Found</h1>")

    # Nested directory with index
    sub = static / "css"
    sub.mkdir()
    (sub / "main.css").write_text("h1 { font-size: 2em; }")

    docs = static / "docs"
    docs.mkdir()
    (docs / "index.html").write_text("<h1>Docs</h1>")

    return static


# ------------------------------------------------------------------
# Prefix-based serving (existing behaviour)
# ------------------------------------------------------------------


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

    async def test_path_traversal_blocked_root_prefix(self, static_dir) -> None:
        """Path traversal is also blocked for root-level serving."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/../../../etc/passwd")
            assert response.status in (403, 404)


class TestStaticFileHeadRequest:
    async def test_head_serves_file(self, static_dir) -> None:
        """HEAD requests should return headers but the ASGI handler sends body too."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.request("HEAD", "/static/style.css")
            assert response.status == 200
            assert "text/css" in response.content_type


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

    async def test_custom_cache_control(self, static_dir) -> None:
        """The cache_control parameter controls the header value."""
        app = App()
        app.add_middleware(
            StaticFiles(
                directory=static_dir,
                prefix="/static",
                cache_control="no-cache",
            )
        )

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            cc = [v for name, v in response.headers if name == "cache-control"]
            assert cc == ["no-cache"]


# ------------------------------------------------------------------
# Root-level serving and index resolution
# ------------------------------------------------------------------


class TestRootPrefixServing:
    async def test_root_prefix_serves_index(self, static_dir) -> None:
        """prefix='/' serves index.html for the root path."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<h1>Home</h1>" in response.text

    async def test_root_prefix_serves_file(self, static_dir) -> None:
        """prefix='/' serves files at the root level."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/style.css")
            assert response.status == 200
            assert "body { color: red; }" in response.text

    async def test_root_prefix_serves_nested(self, static_dir) -> None:
        """prefix='/' serves files in nested directories."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/css/main.css")
            assert response.status == 200
            assert "h1 { font-size: 2em; }" in response.text


class TestIndexResolution:
    async def test_subdirectory_index(self, static_dir) -> None:
        """/docs/ serves docs/index.html."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/docs/")
            assert response.status == 200
            assert "<h1>Docs</h1>" in response.text

    async def test_trailing_slash_redirect(self, static_dir) -> None:
        """/docs redirects to /docs/ when docs/index.html exists."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        async with TestClient(app) as client:
            response = await client.get("/docs")
            assert response.status == 301
            location = [v for name, v in response.headers if name == "location"]
            assert location == ["/docs/"]

    async def test_directory_without_index_falls_through(self, static_dir) -> None:
        """A directory with no index.html falls through."""
        # css/ has no index.html
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        @app.route("/css/")
        def css_route():
            return "css route"

        async with TestClient(app) as client:
            response = await client.get("/css/")
            assert response.status == 200
            assert response.text == "css route"

    async def test_prefix_index_resolution(self, static_dir) -> None:
        """Index resolution works with non-root prefixes too."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/site"))

        async with TestClient(app) as client:
            response = await client.get("/site/docs/")
            assert response.status == 200
            assert "<h1>Docs</h1>" in response.text

    async def test_custom_index_filename(self, tmp_path) -> None:
        """The index parameter controls which file is served for directories."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "default.htm").write_text("<h1>Default</h1>")

        app = App()
        app.add_middleware(
            StaticFiles(
                directory=site,
                prefix="/",
                index="default.htm",
            )
        )

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<h1>Default</h1>" in response.text

    async def test_root_without_index_falls_through(self, tmp_path) -> None:
        """GET / falls through when the root has no index file."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "about.html").write_text("about")

        app = App()
        app.add_middleware(StaticFiles(directory=site, prefix="/"))

        @app.route("/")
        def home():
            return "dynamic home"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert response.text == "dynamic home"


# ------------------------------------------------------------------
# Custom 404 page
# ------------------------------------------------------------------


class TestCustomNotFoundPage:
    async def test_custom_404_page(self, static_dir) -> None:
        """When not_found_page is set, serves it with 404 status."""
        app = App()
        app.add_middleware(
            StaticFiles(
                directory=static_dir,
                prefix="/",
                not_found_page="404.html",
            )
        )

        async with TestClient(app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404
            assert "<h1>Not Found</h1>" in response.text

    async def test_without_not_found_page_falls_through(self, static_dir) -> None:
        """Without not_found_page, missing files fall through."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/"))

        @app.route("/fallback")
        def fallback():
            return "dynamic fallback"

        async with TestClient(app) as client:
            response = await client.get("/fallback")
            assert response.status == 200
            assert response.text == "dynamic fallback"

    async def test_missing_404_page_falls_through(self, static_dir) -> None:
        """If not_found_page file doesn't exist, still falls through."""
        app = App()
        app.add_middleware(
            StaticFiles(
                directory=static_dir,
                prefix="/",
                not_found_page="missing.html",
            )
        )

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            # Request a file that doesn't exist
            response = await client.get("/nope.css")
            # Should fall through to 404 from the router (no custom page found)
            assert response.status == 404

    async def test_not_found_page_traversal_blocked(self, static_dir) -> None:
        """Path traversal in not_found_page is blocked."""
        app = App()
        app.add_middleware(
            StaticFiles(
                directory=static_dir,
                prefix="/",
                not_found_page="../../../etc/passwd",
            )
        )

        async with TestClient(app) as client:
            # not_found_page resolves outside directory — falls through
            response = await client.get("/nonexistent")
            assert response.status == 404

    async def test_custom_404_lets_routes_through(self, static_dir) -> None:
        """Dynamic routes take priority over the custom 404 page."""
        app = App()
        app.add_middleware(
            StaticFiles(
                directory=static_dir,
                prefix="/",
                not_found_page="404.html",
            )
        )

        @app.route("/api/health")
        def health():
            return {"status": "ok"}

        async with TestClient(app) as client:
            response = await client.get("/api/health")
            assert response.status == 200
            assert "ok" in response.text

"""Tests for static file serving middleware."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
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


# ------------------------------------------------------------------
# Config-driven static serving (static_dir in AppConfig)
# ------------------------------------------------------------------


class TestConfigDrivenStaticServing:
    """When AppConfig.static_dir is set and directory exists, Chirp auto-adds StaticFiles."""

    async def test_static_dir_serves_files_without_add_middleware(self, static_dir: Path) -> None:
        """AppConfig(static_dir=...) serves files without explicit add_middleware."""
        app = App(config=AppConfig(static_dir=static_dir))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            assert response.status == 200
            assert "text/css" in response.content_type
            assert "body { color: red; }" in response.text

    async def test_static_dir_with_path_object(self, static_dir: Path) -> None:
        """static_dir accepts Path objects."""
        app = App(config=AppConfig(static_dir=Path(static_dir)))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/app.js")
            assert response.status == 200
            assert "console.log" in response.text

    async def test_static_dir_none_no_staticfiles(self, static_dir: Path) -> None:
        """static_dir=None disables auto StaticFiles; /static/... falls through to 404."""
        app = App(config=AppConfig(static_dir=None))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            assert response.status == 404

    async def test_static_dir_missing_directory_no_middleware(self, tmp_path: Path) -> None:
        """When static_dir points to non-existent dir, no StaticFiles added."""
        missing = tmp_path / "nonexistent"
        app = App(config=AppConfig(static_dir=missing))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/foo.css")
            assert response.status == 404

    async def test_static_url_custom_prefix(self, static_dir: Path) -> None:
        """static_url controls the URL prefix."""
        app = App(config=AppConfig(static_dir=static_dir, static_url="/assets"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/assets/style.css")
            assert response.status == 200
            assert "body { color: red; }" in response.text


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


# ------------------------------------------------------------------
# Streaming + conditional GET / Range (#178)
# ------------------------------------------------------------------


def _header(response, name):
    """First header value (case-insensitive) from a TestClient Response."""
    target = name.lower()
    for n, v in response.headers:
        if n.lower() == target:
            return v
    return None


class TestStaticConditionalGet:
    async def test_etag_and_last_modified_emitted(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
            assert response.status == 200
            assert _header(response, "ETag") is not None
            assert _header(response, "Last-Modified") is not None
            assert _header(response, "Accept-Ranges") == "bytes"
            assert "body { color: red; }" in response.text

    async def test_if_none_match_returns_304(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            first = await client.get("/static/style.css")
            etag = _header(first, "ETag")
            assert etag is not None

            second = await client.get("/static/style.css", headers={"If-None-Match": etag})
            assert second.status == 304
            assert second.text == ""  # empty body on 304

    async def test_if_none_match_wildcard_returns_304(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css", headers={"If-None-Match": "*"})
            assert response.status == 304

    async def test_if_modified_since_returns_304(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            first = await client.get("/static/style.css")
            last_modified = _header(first, "Last-Modified")
            assert last_modified is not None

            second = await client.get(
                "/static/style.css", headers={"If-Modified-Since": last_modified}
            )
            assert second.status == 304

    async def test_stale_if_modified_since_returns_200(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get(
                "/static/style.css",
                headers={"If-Modified-Since": "Mon, 01 Jan 1990 00:00:00 GMT"},
            )
            assert response.status == 200
            assert "body { color: red; }" in response.text


class TestStaticRange:
    async def test_range_returns_206_and_slice(self, static_dir) -> None:
        # "body { color: red; }" — bytes 0-3 == "body"
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css", headers={"Range": "bytes=0-3"})
            assert response.status == 206
            assert response.text == "body"
            content_range = _header(response, "Content-Range")
            assert content_range is not None
            assert content_range.startswith("bytes 0-3/")

    async def test_suffix_range(self, static_dir) -> None:
        full = "body { color: red; }"
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css", headers={"Range": "bytes=-4"})
            assert response.status == 206
            assert response.text == full[-4:]

    async def test_unsatisfiable_range_returns_416(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css", headers={"Range": "bytes=9999-10000"})
            assert response.status == 416
            content_range = _header(response, "Content-Range")
            assert content_range is not None
            assert content_range.startswith("bytes */")

    async def test_multi_range_falls_back_to_200(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css", headers={"Range": "bytes=0-1,3-4"})
            # Multi-range is unsupported — serve the full body, not a malformed
            # multipart/byteranges response.
            assert response.status == 200
            assert "body { color: red; }" in response.text


class TestStaticHeadConditional:
    async def test_head_sends_no_body(self, static_dir) -> None:
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.request("HEAD", "/static/style.css")
            assert response.status == 200
            assert "text/css" in response.content_type
            assert _header(response, "ETag") is not None
            assert response.text == ""  # HEAD: headers only, no body


class TestStaticStreamingLargeFile:
    async def test_large_file_streamed_intact(self, tmp_path) -> None:
        """A file above the stream threshold is served byte-for-byte via the
        chunked read path."""
        static = tmp_path / "static"
        static.mkdir()
        # Deterministic, larger-than-threshold binary payload.
        payload = bytes(range(256)) * 5000  # ~1.28 MiB
        (static / "big.bin").write_bytes(payload)

        app = App()
        app.add_middleware(
            StaticFiles(directory=static, prefix="/static", stream_threshold=64 * 1024)
        )

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/big.bin")
            assert response.status == 200
            assert response.body == payload
            assert len(response.body) == len(payload)

    async def test_small_file_single_read_path(self, tmp_path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        payload = b"small"
        (static / "small.bin").write_bytes(payload)

        app = App()
        app.add_middleware(
            StaticFiles(directory=static, prefix="/static", stream_threshold=1024 * 1024)
        )

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/small.bin")
            assert response.status == 200
            assert response.body == payload


class TestStaticCustom404NotConditional:
    async def test_custom_404_does_not_304(self, static_dir) -> None:
        """A custom 404 page is served with status 404 and never 304s, even
        when the client sends a matching validator-style header."""
        app = App()
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/", not_found_page="404.html"))

        async with TestClient(app) as client:
            response = await client.get("/nonexistent", headers={"If-None-Match": "*"})
            assert response.status == 404
            assert "<h1>Not Found</h1>" in response.text


class TestStaticStreamingContract:
    async def test_negative_threshold_warns(self, tmp_path) -> None:
        from chirp.contracts.rules_static_streaming import check_static_streaming

        mw = StaticFiles(directory=tmp_path, prefix="/static", stream_threshold=-1)
        issues = check_static_streaming([mw])
        assert any(issue.category == "static_streaming" for issue in issues)

    async def test_sane_threshold_no_warning(self, tmp_path) -> None:
        from chirp.contracts.rules_static_streaming import check_static_streaming

        mw = StaticFiles(directory=tmp_path, prefix="/static")
        issues = check_static_streaming([mw])
        assert issues == []

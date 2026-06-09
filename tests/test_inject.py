"""Tests for HTML injection middleware."""

from chirp import App
from chirp.http.response import Response
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
    async def test_skips_explicit_fragment_intent(self) -> None:
        """Response render intent overrides request heuristics."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/")
        def index():
            return Response(body="<div>fragment</div>", render_intent="fragment")

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert SCRIPT_TAG not in response.text

    async def test_skips_htmx_fragment_requests(self) -> None:
        """HTMX requests should not receive global HTML injections."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert response.text == "<div>fragment</div>"
            assert SCRIPT_TAG not in response.text

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
        (site / "index.html").write_text("<html><body><p>Hello</p></body></html>")

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


def _header(response, name):
    """First header value (case-insensitive) from a TestClient Response."""
    target = name.lower()
    for n, v in response.headers:
        if n.lower() == target:
            return v
    return None


def _static_app(tmp_path, *middleware):
    """App serving a single injected static HTML page from tmp_path."""
    from chirp.middleware.static import StaticFiles

    site = tmp_path / "public"
    site.mkdir(parents=True)
    (site / "index.html").write_text("<html><body><p>Hello</p></body></html>")

    app = App()
    for mw in middleware:
        app.add_middleware(mw)
    app.add_middleware(StaticFiles(directory=site, prefix="/"))
    return app


class TestInjectedStaticConditionalGet:
    """#198: injected static HTML must keep conditional-GET (ETag/304/Last-Modified)."""

    async def test_emits_etag_and_last_modified(self, tmp_path) -> None:
        app = _static_app(tmp_path, HTMLInject(SCRIPT_TAG))
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert SCRIPT_TAG + "</body>" in response.text
            assert _header(response, "ETag") is not None
            assert _header(response, "Last-Modified") is not None

    async def test_etag_covers_injected_body_not_file(self, tmp_path) -> None:
        """The ETag must describe the served (injected) bytes, not the file."""
        app_plain = _static_app(tmp_path / "a", HTMLInject(SCRIPT_TAG))
        app_other = _static_app(tmp_path / "b", HTMLInject("<!--different snippet-->"))
        async with TestClient(app_plain) as c1, TestClient(app_other) as c2:
            e1 = _header(await c1.get("/"), "ETag")
            e2 = _header(await c2.get("/"), "ETag")
            assert e1 is not None
            assert e2 is not None
            # Same file bytes, different snippet -> different ETag.
            assert e1 != e2

    async def test_if_none_match_returns_304(self, tmp_path) -> None:
        app = _static_app(tmp_path, HTMLInject(SCRIPT_TAG))
        async with TestClient(app) as client:
            first = await client.get("/")
            etag = _header(first, "ETag")
            assert etag is not None
            second = await client.get("/", headers={"If-None-Match": etag})
            assert second.status == 304
            assert second.text == ""

    async def test_if_modified_since_returns_304(self, tmp_path) -> None:
        app = _static_app(tmp_path, HTMLInject(SCRIPT_TAG))
        async with TestClient(app) as client:
            first = await client.get("/")
            last_modified = _header(first, "Last-Modified")
            assert last_modified is not None
            second = await client.get("/", headers={"If-Modified-Since": last_modified})
            assert second.status == 304

    async def test_does_not_advertise_accept_ranges(self, tmp_path) -> None:
        """Injected HTML drops Range — on-disk offsets shift after injection."""
        app = _static_app(tmp_path, HTMLInject(SCRIPT_TAG))
        async with TestClient(app) as client:
            response = await client.get("/")
            assert _header(response, "Accept-Ranges") is None

    async def test_nonce_snippet_skips_etag_but_keeps_last_modified(self, tmp_path) -> None:
        """A per-request nonce snippet must not get a strong ETag (would cache a
        dead nonce), but Last-Modified is still safe."""
        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        app = _static_app(
            tmp_path,
            HTMLInject(lambda nonce: f'<script nonce="{nonce}">x</script>'),
            CSPNonceMiddleware(),
        )
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert _header(response, "ETag") is None
            assert _header(response, "Last-Modified") is not None

    async def test_nonce_snippet_never_returns_304(self, tmp_path) -> None:
        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        app = _static_app(
            tmp_path,
            HTMLInject(lambda nonce: f'<script nonce="{nonce}">x</script>'),
            CSPNonceMiddleware(),
        )
        async with TestClient(app) as client:
            first = await client.get("/")
            last_modified = _header(first, "Last-Modified")
            assert _header(first, "ETag") is None
            assert last_modified is not None
            # A valid If-Modified-Since must NOT short-circuit to 304 for a
            # nonce body — that would serve a body carrying a dead nonce.
            second = await client.get("/", headers={"If-Modified-Since": last_modified})
            assert second.status == 200
            assert "<script nonce=" in second.text

    async def test_alpine_injected_static_html_keeps_caching(self, tmp_path) -> None:
        from chirp.middleware.inject import AlpineInject

        # Alpine bootstrap with a constant snippet (no nonce in scope) is stable.
        app = _static_app(tmp_path, AlpineInject("<!--ALPINE-->"))
        async with TestClient(app) as client:
            first = await client.get("/")
            assert "<!--ALPINE-->" in first.text
            etag = _header(first, "ETag")
            assert etag is not None
            second = await client.get("/", headers={"If-None-Match": etag})
            assert second.status == 304


class TestHTMLInjectFullPageOnly:
    async def test_full_page_only_injects_when_target_present(self) -> None:
        """full_page_only=True still injects when </body> is found."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG, full_page_only=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert SCRIPT_TAG + "</body>" in response.text

    async def test_full_page_only_skips_when_target_absent(self) -> None:
        """full_page_only=True does NOT append when </body> is absent."""
        app = App()
        app.add_middleware(HTMLInject(SCRIPT_TAG, full_page_only=True))

        @app.route("/")
        def index():
            return "<h1>Fragment</h1>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.text == "<h1>Fragment</h1>"
            assert SCRIPT_TAG not in response.text


class TestHTMLInjectExport:
    def test_importable_from_middleware_package(self) -> None:
        """HTMLInject is importable from chirp.middleware."""
        from chirp.middleware import HTMLInject as Imported

        assert Imported is HTMLInject

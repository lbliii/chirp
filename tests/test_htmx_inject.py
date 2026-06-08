"""Tests for htmx injection — config, snippet builder, injection, dedup, streaming."""

import re

from chirp import App
from chirp.config import AppConfig
from chirp.server.htmx_inject import SSE_EXTENSION_VERSION, htmx_snippet
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Unit tests — htmx_snippet
# ---------------------------------------------------------------------------


class TestHtmxSnippet:
    def test_default_builds_script_tag(self) -> None:
        s = htmx_snippet("2.0.4")
        assert 'src="https://unpkg.com/htmx.org@2.0.4"' in s
        assert 'data-chirp="htmx"' in s

    def test_default_omits_sse_extension(self) -> None:
        s = htmx_snippet("2.0.4")
        assert "htmx-ext-sse" not in s

    def test_sse_opt_in_includes_extension(self) -> None:
        s = htmx_snippet("2.0.4", sse=True)
        assert f"htmx-ext-sse@{SSE_EXTENSION_VERSION}/sse.js" in s
        assert 'data-chirp="htmx-sse"' in s

    def test_sse_false_excludes_extension(self) -> None:
        s = htmx_snippet("2.0.4", sse=False)
        assert "htmx-ext-sse" not in s

    def test_uses_config_version(self) -> None:
        """The provided core version is threaded into the unpkg URL."""
        s = htmx_snippet("2.0.3")
        assert 'src="https://unpkg.com/htmx.org@2.0.3"' in s

    def test_core_is_not_module_scoped(self) -> None:
        """htmx must remain a classic blocking script (global window.htmx)."""
        s = htmx_snippet("2.0.4")
        assert 'type="module"' not in s

    def test_no_jsdelivr_bare_npm_path(self) -> None:
        """htmx ships from unpkg, not jsDelivr — guard against the CDN footgun.

        A bare ``cdn.jsdelivr.net/npm/htmx.org@VER`` path resolves to package
        ``main`` (a CommonJS module) and breaks silently in the browser. htmx's
        proven build is unpkg's ``htmx.org@VER`` IIFE bundle.
        """
        s = htmx_snippet("2.0.4", sse=True)
        assert "cdn.jsdelivr.net" not in s
        # The proven, working forms must be present verbatim.
        assert "unpkg.com/htmx.org@2.0.4" in s
        assert f"unpkg.com/htmx-ext-sse@{SSE_EXTENSION_VERSION}/sse.js" in s

    def test_bad_url_pattern_detects_known_bad_url(self) -> None:
        """Guard: regex must match a known-bad jsDelivr bare URL (not vacuous)."""
        bad = 'src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4"'
        assert re.findall(r"cdn\.jsdelivr\.net/npm/htmx", bad) == ["cdn.jsdelivr.net/npm/htmx"]


# ---------------------------------------------------------------------------
# Integration tests — injection via App._freeze()
# ---------------------------------------------------------------------------


class TestHtmxInjection:
    async def test_injected_when_htmx_enabled(self) -> None:
        """htmx=True injects the htmx script in full-page HTML."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="htmx"' in response.text
            assert "unpkg.com/htmx.org" in response.text

    async def test_not_injected_when_htmx_disabled(self) -> None:
        """htmx=False (default) does not inject."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "unpkg.com/htmx.org" not in response.text

    async def test_not_injected_on_fragment(self) -> None:
        """htmx fragment requests do not get the injected script."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "unpkg.com/htmx.org" not in response.text

    async def test_not_injected_on_json(self) -> None:
        """JSON responses are untouched."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/api")
        def api():
            return {"key": "value"}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert "unpkg.com/htmx.org" not in response.text

    async def test_uses_config_version(self) -> None:
        """htmx_version from config is used in the script URL."""
        app = App(config=AppConfig(htmx=True, htmx_version="2.0.3"))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "htmx.org@2.0.3" in response.text

    async def test_sse_extension_injected_when_enabled(self) -> None:
        """htmx_sse=True also injects the SSE extension script."""
        app = App(config=AppConfig(htmx=True, htmx_sse=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "htmx-ext-sse" in response.text
            assert 'data-chirp="htmx-sse"' in response.text

    async def test_sse_extension_absent_by_default(self) -> None:
        """htmx_sse defaults False — no SSE extension even when htmx=True."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "htmx-ext-sse" not in response.text


# ---------------------------------------------------------------------------
# HtmxInject deduplication tests
# ---------------------------------------------------------------------------


class TestHtmxInjectDedup:
    async def test_skips_injection_when_htmx_already_present(self) -> None:
        """HtmxInject does not double-inject if page already has the marker."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return (
                "<html><body>"
                '<script src="https://unpkg.com/htmx.org@2.0.4" data-chirp="htmx"></script>'
                "</body></html>"
            )

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            body = response.text
            count = body.count('data-chirp="htmx"')
            assert count == 1, f"Expected 1 htmx marker, found {count}"

    async def test_injects_when_htmx_not_present(self) -> None:
        """HtmxInject adds htmx to a page that lacks it."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<html><body><h1>No htmx here</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="htmx"' in response.text


# ---------------------------------------------------------------------------
# Streaming rewrite — HtmxInject over a StreamingResponse (Suspense shell)
# ---------------------------------------------------------------------------


async def test_htmx_middleware_wraps_streaming_response() -> None:
    """HtmxInject rewrites StreamingResponse chunks (same as Suspense output)."""
    from chirp.http.response import StreamingResponse
    from chirp.middleware.inject import HtmxInject

    class FakeRequest:
        is_fragment = False
        is_htmx = False

    snippet = htmx_snippet("2.0.4")
    mw = HtmxInject(snippet, full_page_only=True)

    async def next_ok(_req: object) -> StreamingResponse:
        def chunks():
            yield "<!DOCTYPE html><html><head></head><body>ok"
            yield "</body></html>"

        return StreamingResponse(chunks=chunks())

    resp = await mw(FakeRequest(), next_ok)
    assert isinstance(resp, StreamingResponse)
    parts: list[str] = [chunk async for chunk in resp.chunks]
    text = "".join(parts)
    assert 'data-chirp="htmx"' in text
    assert "unpkg.com/htmx.org" in text


async def test_htmx_middleware_streaming_split_delimiter() -> None:
    """Injection works when </body> is split across stream chunks."""
    from chirp.http.response import StreamingResponse
    from chirp.middleware.inject import HtmxInject

    class FakeRequest:
        is_fragment = False
        is_htmx = False

    mw = HtmxInject(htmx_snippet("2.0.4"), full_page_only=True)

    async def next_ok(_req: object) -> StreamingResponse:
        def chunks():
            yield "<html><body><p>z</p></bo"
            yield "dy></html>"

        return StreamingResponse(chunks=chunks())

    resp = await mw(FakeRequest(), next_ok)
    assert isinstance(resp, StreamingResponse)
    text = "".join([chunk async for chunk in resp.chunks])
    assert 'data-chirp="htmx"' in text
    assert "</p>" in text.split("</body>")[0]


async def test_htmx_middleware_streaming_dedup() -> None:
    """A stream already carrying the marker before </body> is left unchanged."""
    from chirp.http.response import StreamingResponse
    from chirp.middleware.inject import HtmxInject

    class FakeRequest:
        is_fragment = False
        is_htmx = False

    mw = HtmxInject(htmx_snippet("2.0.4"), full_page_only=True)

    async def next_ok(_req: object) -> StreamingResponse:
        def chunks():
            yield '<html><body><script data-chirp="htmx"></script>'
            yield "</body></html>"

        return StreamingResponse(chunks=chunks())

    resp = await mw(FakeRequest(), next_ok)
    assert isinstance(resp, StreamingResponse)
    text = "".join([chunk async for chunk in resp.chunks])
    assert text.count('data-chirp="htmx"') == 1
    assert "unpkg.com/htmx.org" not in text


# ---------------------------------------------------------------------------
# Robust dedup — marker-less htmx <script> already on the page (Fix #2)
# ---------------------------------------------------------------------------


class TestHtmxInjectRobustDedup:
    async def test_marker_less_htmx_script_is_not_double_loaded(self) -> None:
        """A hand-provisioned htmx <script> WITHOUT the data-chirp marker must
        still dedup — htmx must not be loaded twice.

        Scaffolded/third-party pages may ship ``<script src=".../htmx...">``
        with no Chirp marker. ``HtmxInject`` recognizes any htmx src and skips
        injection so ``AppConfig(htmx=True)`` over such a page does not produce
        two htmx runtimes (double-binding every hx-* attribute)."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return (
                "<html><body>"
                # No data-chirp marker — only the src heuristic can catch this.
                '<script src="https://unpkg.com/htmx.org@2.0.4"></script>'
                "</body></html>"
            )

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            body = response.text
            # Exactly one htmx core script — no second injected copy.
            assert body.count("unpkg.com/htmx.org") == 1
            assert 'data-chirp="htmx"' not in body

    async def test_self_hosted_marker_less_script_dedups(self) -> None:
        """A self-hosted ``/static/htmx.min.js`` (no marker) also dedups."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return '<html><body><script src="/static/htmx.min.js"></script></body></html>'

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            body = response.text
            assert body.count("htmx.min.js") == 1
            # Chirp did not inject its own unpkg copy.
            assert "unpkg.com/htmx.org" not in body

    async def test_streaming_marker_less_script_dedups(self) -> None:
        """Streaming path also dedups a marker-less htmx <script>."""
        from chirp.http.response import StreamingResponse
        from chirp.middleware.inject import HtmxInject

        class FakeRequest:
            is_fragment = False
            is_htmx = False

        mw = HtmxInject(htmx_snippet("2.0.4"), full_page_only=True)

        async def next_ok(_req: object) -> StreamingResponse:
            def chunks():
                yield '<html><body><script src="https://unpkg.com/htmx.org@2.0.4"></script>'
                yield "</body></html>"

            return StreamingResponse(chunks=chunks())

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, StreamingResponse)
        text = "".join([chunk async for chunk in resp.chunks])
        assert text.count("unpkg.com/htmx.org") == 1
        assert 'data-chirp="htmx"' not in text


# ---------------------------------------------------------------------------
# Render-intent branch coverage (Fix #4)
# ---------------------------------------------------------------------------


class TestHtmxInjectRenderIntentBranches:
    async def test_hx_request_full_page_template_is_injected(self) -> None:
        """An HX-Request to a route returning a full-page Template (render_intent
        ``full_page``) must STILL get htmx injected.

        A ``Template`` return is always a full page (e.g. an hx-boosted
        navigation). Suppressing injection for every htmx request would strip
        htmx from boosted full-page swaps — over-suppression. Only ``fragment``
        intent (and ``unknown`` + htmx) is skipped."""
        import tempfile
        from pathlib import Path

        from chirp.templating.returns import Template

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "page.html").write_text("<html><body><h1>Full page</h1></body></html>")
            app = App(config=AppConfig(htmx=True, template_dir=tmp))

            @app.route("/")
            def index():
                return Template("page.html")

            async with TestClient(app) as client:
                response = await client.get("/", headers={"HX-Request": "true"})
                assert response.status == 200
                # A Template render is full_page intent; injection must still
                # fire under HX-Request (boosted full-page navigation). The
                # presence of the marker is proof the middleware saw full_page
                # and did NOT take the "unknown + htmx -> skip" branch.
                assert 'data-chirp="htmx"' in response.text
                assert "unpkg.com/htmx.org" in response.text

    async def test_fragment_streaming_response_is_not_injected(self) -> None:
        """A StreamingResponse with render_intent ``fragment`` must NOT get htmx
        injected — fragment swaps are inserted into an already-provisioned page."""
        from chirp.http.response import StreamingResponse
        from chirp.middleware.inject import HtmxInject

        class FakeRequest:
            is_fragment = True
            is_htmx = True

        mw = HtmxInject(htmx_snippet("2.0.4"), full_page_only=True)

        async def next_fragment(_req: object) -> StreamingResponse:
            async def chunks():
                yield "<div id='row'>fragment</div>"

            return StreamingResponse(chunks=chunks(), render_intent="fragment")

        resp = await mw(FakeRequest(), next_fragment)
        assert isinstance(resp, StreamingResponse)
        text = "".join([chunk async for chunk in resp.chunks])
        assert "unpkg.com/htmx.org" not in text
        assert 'data-chirp="htmx"' not in text


# ---------------------------------------------------------------------------
# Version lockstep — injector defaults must match scaffold literal URLs (Fix #4)
# ---------------------------------------------------------------------------


def test_injector_versions_match_scaffold_template_urls() -> None:
    """The injector's default htmx core version and SSE_EXTENSION_VERSION must
    match the literal unpkg URLs the chirpui scaffold + chirp/layouts/shell.html
    ship.

    Mode A (injection) and the scaffold's hand-written <script> tags are two
    paths to the same runtime. If a future version bump touches one path but not
    the other, a scaffolded app that later opts into AppConfig(htmx=True) could
    load two different htmx versions. This test pins the two paths together so
    such drift fails loudly at test time."""
    from pathlib import Path

    from chirp.config import AppConfig

    default_core = AppConfig().htmx_version
    expected_core_url = f"https://unpkg.com/htmx.org@{default_core}"
    expected_sse_url = f"https://unpkg.com/htmx-ext-sse@{SSE_EXTENSION_VERSION}/sse.js"

    # The snippet the injector would emit uses exactly these URLs.
    snippet = htmx_snippet(default_core, sse=True)
    assert expected_core_url in snippet
    assert expected_sse_url in snippet

    repo_root = Path(__file__).resolve().parents[1]
    scaffold = (repo_root / "src/chirp/cli/templates/v2.py").read_text()
    shell = (repo_root / "src/chirp/templating/macros/chirp/layouts/shell.html").read_text()

    for name, text in (("scaffold v2.py", scaffold), ("shell.html", shell)):
        assert expected_core_url in text, f"{name} htmx core URL drifted from injector default"
        assert expected_sse_url in text, f"{name} htmx SSE URL drifted from injector default"

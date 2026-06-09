"""Tests for opt-in htmx injection — AppConfig(htmx=...) mirrors the Alpine path.

Covers: the ``htmx_snippet`` builder, default-off, opt-in injection,
``data-chirp="htmx"`` dedup, StreamingResponse chunk rewrite, and the live
per-request CSP nonce on the injected ``<script>``.
"""

import re

from chirp import App
from chirp.config import AppConfig
from chirp.server.htmx import htmx_snippet
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Unit tests — htmx_snippet
# ---------------------------------------------------------------------------


class TestHtmxSnippet:
    def test_builds_script_tag(self) -> None:
        s = htmx_snippet("2.0.4")
        assert 'src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js"' in s
        assert 'data-chirp="htmx"' in s
        assert "defer" in s

    def test_uses_explicit_dist_path(self) -> None:
        """The src must use the explicit /dist path — the framework CDN
        convention (same explicit-/dist rule enforced for Alpine). htmx's bare
        package main is browser-safe (unlike Alpine's CJS module), so for htmx
        this pins the minified browser bundle for consistency."""
        s = htmx_snippet("2.0.4")
        assert "htmx.org@2.0.4/dist/htmx.min.js" in s

    def test_no_bare_package_url(self) -> None:
        s = htmx_snippet("2.0.4")
        bare = re.findall(r'src="[^"]+@[0-9.]+"', s)
        assert not bare, f"Bare package script URL (no /dist/...): {bare}"

    def test_version_follows_argument(self) -> None:
        s = htmx_snippet("2.1.0")
        assert "htmx.org@2.1.0/dist/htmx.min.js" in s

    def test_no_nonce_by_default(self) -> None:
        s = htmx_snippet("2.0.4")
        assert "nonce=" not in s

    def test_carries_nonce_when_given(self) -> None:
        s = htmx_snippet("2.0.4", nonce="ABC123")
        assert 'nonce="ABC123"' in s


# ---------------------------------------------------------------------------
# Integration tests — injection via App._freeze()
# ---------------------------------------------------------------------------


class TestHtmxInjection:
    async def test_injected_when_htmx_enabled(self) -> None:
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="htmx"' in response.text
            assert "cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js" in response.text

    async def test_not_injected_when_htmx_disabled(self) -> None:
        """htmx=False (default) does not inject."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "htmx.org" not in response.text

    async def test_not_injected_on_fragment(self) -> None:
        """htmx fragment requests do not get the htmx core injected."""
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "htmx.org" not in response.text

    async def test_not_injected_on_json(self) -> None:
        app = App(config=AppConfig(htmx=True))

        @app.route("/api")
        def api():
            return {"key": "value"}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert "htmx.org" not in response.text

    async def test_uses_config_version(self) -> None:
        app = App(config=AppConfig(htmx=True, htmx_version="2.1.0"))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "htmx.org@2.1.0" in response.text


# ---------------------------------------------------------------------------
# Dedup tests — data-chirp="htmx"
# ---------------------------------------------------------------------------


class TestHtmxInjectDedup:
    async def test_skips_injection_when_htmx_already_present(self) -> None:
        """No double-inject if the page already carries data-chirp="htmx"."""
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
            count = response.text.count('data-chirp="htmx"')
            assert count == 1, f"Expected 1 htmx marker, found {count}"

    async def test_injects_when_htmx_not_present(self) -> None:
        app = App(config=AppConfig(htmx=True))

        @app.route("/")
        def index():
            return "<html><body><h1>No htmx here</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="htmx"' in response.text


# ---------------------------------------------------------------------------
# Streaming chunk rewrite — Suspense-style StreamingResponse
# ---------------------------------------------------------------------------


class TestHtmxStreamingInject:
    async def test_streaming_response_rewritten(self) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.middleware.inject import StreamingHTMLInject

        class FakeRequest:
            is_htmx = False

        mw = StreamingHTMLInject(
            lambda nonce: htmx_snippet("2.0.4", nonce=nonce),
            full_page_only=True,
            dedup_marker='data-chirp="htmx"',
        )

        async def next_ok(_req: object) -> StreamingResponse:
            def chunks():
                yield "<!DOCTYPE html><html><head></head><body>ok"
                yield "</body></html>"

            return StreamingResponse(chunks=chunks())

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, StreamingResponse)
        text = "".join([chunk async for chunk in resp.chunks])
        assert 'data-chirp="htmx"' in text
        assert "htmx.org@2.0.4/dist/htmx.min.js" in text
        # Snippet lands before the first </body>.
        assert text.index('data-chirp="htmx"') < text.index("</body>")

    async def test_streaming_dedup_skips(self) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.middleware.inject import StreamingHTMLInject

        class FakeRequest:
            is_htmx = False

        mw = StreamingHTMLInject(
            lambda nonce: htmx_snippet("2.0.4", nonce=nonce),
            full_page_only=True,
            dedup_marker='data-chirp="htmx"',
        )

        async def next_ok(_req: object) -> StreamingResponse:
            def chunks():
                yield '<html><body><script data-chirp="htmx"></script>'
                yield "</body></html>"

            return StreamingResponse(chunks=chunks())

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, StreamingResponse)
        text = "".join([chunk async for chunk in resp.chunks])
        assert text.count('data-chirp="htmx"') == 1


# ---------------------------------------------------------------------------
# CSP nonce — the injected <script> carries the live per-request nonce
# ---------------------------------------------------------------------------


class TestHtmxInjectNonce:
    @staticmethod
    def _factory():
        return lambda nonce: htmx_snippet("2.0.4", nonce=nonce)

    async def test_buffered_carries_live_nonce(self) -> None:
        from chirp.http.response import Response
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce
        from chirp.middleware.inject import StreamingHTMLInject

        class FakeRequest:
            is_htmx = False

        mw = StreamingHTMLInject(
            self._factory(), full_page_only=True, dedup_marker='data-chirp="htmx"'
        )

        async def next_ok(_req: object) -> Response:
            return Response(
                body="<html><body><h1>Hi</h1></body></html>",
                content_type="text/html; charset=utf-8",
            )

        token = _set_csp_nonce("LIVE-NONCE-123")
        try:
            resp = await mw(FakeRequest(), next_ok)
        finally:
            _reset_csp_nonce(token)

        assert isinstance(resp, Response)
        text = resp.body if isinstance(resp.body, str) else resp.body.decode()
        assert 'nonce="LIVE-NONCE-123"' in text
        assert 'data-chirp="htmx"' in text

    async def test_streaming_carries_live_nonce(self) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce
        from chirp.middleware.inject import StreamingHTMLInject

        class FakeRequest:
            is_htmx = False

        mw = StreamingHTMLInject(
            self._factory(), full_page_only=True, dedup_marker='data-chirp="htmx"'
        )

        async def next_ok(_req: object) -> StreamingResponse:
            def chunks():
                yield "<!DOCTYPE html><html><head></head><body>ok"
                yield "</body></html>"

            return StreamingResponse(chunks=chunks())

        token = _set_csp_nonce("STREAM-NONCE-456")
        try:
            resp = await mw(FakeRequest(), next_ok)
            assert isinstance(resp, StreamingResponse)
            parts = [chunk async for chunk in resp.chunks]
        finally:
            _reset_csp_nonce(token)

        text = "".join(parts)
        assert 'nonce="STREAM-NONCE-456"' in text
        assert "htmx.org@2.0.4/dist/htmx.min.js" in text

    async def test_no_nonce_when_disabled(self) -> None:
        from chirp.http.response import Response
        from chirp.middleware.inject import StreamingHTMLInject

        class FakeRequest:
            is_htmx = False

        mw = StreamingHTMLInject(
            self._factory(), full_page_only=True, dedup_marker='data-chirp="htmx"'
        )

        async def next_ok(_req: object) -> Response:
            return Response(
                body="<html><body>x</body></html>",
                content_type="text/html; charset=utf-8",
            )

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, Response)
        text = resp.body if isinstance(resp.body, str) else resp.body.decode()
        assert "nonce=" not in text

    async def test_end_to_end_nonce_under_csp_nonce_middleware(self) -> None:
        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        app = App(config=AppConfig(htmx=True))
        app.add_middleware(CSPNonceMiddleware())

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            csp = response.header("content-security-policy") or ""
            m = re.search(r"'nonce-([^']+)'", csp)
            assert m, f"no nonce in CSP header: {csp!r}"
            nonce = m.group(1)
            # The injected htmx core tag carries the live response nonce.
            assert f'nonce="{nonce}" data-chirp="htmx"' in response.text

"""Tests for SecurityHeadersMiddleware — headers on HTML, skip on non-HTML."""

import pytest

from chirp import App
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from chirp.testing import TestClient


def _header(response, name: str) -> str | None:
    for hname, hvalue in response.headers:
        if hname == name:
            return hvalue
    return None


def _make_app() -> App:
    app = App()
    app.add_middleware(SecurityHeadersMiddleware())

    @app.route("/")
    def index():
        return "Hello"

    @app.route("/json")
    def json_route():
        return {"ok": True}

    return app


@pytest.mark.anyio
async def test_html_response_gets_headers() -> None:
    app = _make_app()
    async with TestClient(app) as client:
        response = await client.get("/")
    assert response.status == 200
    assert _header(response, "x-frame-options") == "DENY"
    assert _header(response, "x-content-type-options") == "nosniff"
    assert _header(response, "referrer-policy") == "strict-origin-when-cross-origin"
    assert _header(response, "content-security-policy") is not None
    assert _header(response, "strict-transport-security") is None


@pytest.mark.anyio
async def test_json_response_skipped() -> None:
    app = _make_app()
    async with TestClient(app) as client:
        response = await client.get("/json")
    assert response.status == 200
    assert _header(response, "x-frame-options") is None


@pytest.mark.anyio
async def test_custom_config() -> None:
    app = App()
    app.add_middleware(
        SecurityHeadersMiddleware(
            SecurityHeadersConfig(
                x_frame_options="SAMEORIGIN",
                content_security_policy="default-src 'self'",
                strict_transport_security="max-age=63072000; includeSubDomains",
            )
        )
    )

    @app.route("/")
    def index():
        return "Hello"

    async with TestClient(app) as client:
        response = await client.get("/")
    assert _header(response, "x-frame-options") == "SAMEORIGIN"
    assert _header(response, "content-security-policy") == "default-src 'self'"
    assert _header(response, "strict-transport-security") == "max-age=63072000; includeSubDomains"


# --- CSP allows framework-required script origins ---


class TestDefaultCSPAllowsFrameworkScripts:
    """The default CSP must permit scripts that Chirp's own templates load.

    Chirp layouts load htmx from unpkg.com and Alpine.js from
    cdn.jsdelivr.net.  Inline scripts (dark-mode toggle, Alpine store
    init) also need to run.  If the default CSP blocks any of these the
    framework silently breaks htmx swaps, SSE, and client-side UI.
    """

    @pytest.mark.anyio
    async def test_default_csp_allows_unpkg(self) -> None:
        """htmx is loaded from unpkg.com in shell.html / boost.html."""
        app = _make_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
        csp = _header(resp, "content-security-policy") or ""
        assert "https://unpkg.com" in csp

    @pytest.mark.anyio
    async def test_default_csp_allows_jsdelivr(self) -> None:
        """Alpine.js plugins are loaded from cdn.jsdelivr.net."""
        app = _make_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
        csp = _header(resp, "content-security-policy") or ""
        assert "https://cdn.jsdelivr.net" in csp

    @pytest.mark.anyio
    async def test_default_csp_drops_unsafe_inline(self) -> None:
        """Default CSP no longer ships 'unsafe-inline' (#181).

        Framework inline scripts now carry a live nonce (Suspense streams) or
        are caught by the csp_nonce contract (Alpine bootstrap). The secure
        default is a nonce-able policy, not an inline-allowing one.
        """
        app = _make_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
        csp = _header(resp, "content-security-policy") or ""
        assert "'unsafe-inline'" not in csp

    @pytest.mark.anyio
    async def test_default_csp_no_unsafe_eval(self) -> None:
        """Default CSP should not include unsafe-eval (opt-in via compiler)."""
        app = _make_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
        csp = _header(resp, "content-security-policy") or ""
        assert "'unsafe-eval'" not in csp

    def test_config_default_has_script_src(self) -> None:
        """SecurityHeadersConfig default CSP includes an explicit script-src."""
        cfg = SecurityHeadersConfig()
        assert cfg.content_security_policy is not None
        assert "script-src" in cfg.content_security_policy

    def test_config_default_drops_unsafe_inline(self) -> None:
        """Default CSP no longer ships 'unsafe-inline' (#181)."""
        cfg = SecurityHeadersConfig()
        assert "'unsafe-inline'" not in (cfg.content_security_policy or "")

# --- Static HTML FileResponse must keep security headers (issue #178) ---


class TestStaticFileResponseHeaders:
    """A static .html served via StaticFiles is a ``FileResponse``, not a
    ``Response``/``StreamingResponse``. The middleware must still apply
    security headers — otherwise root-prefix static sites and custom 404
    pages silently lose X-Frame-Options / X-Content-Type-Options /
    Referrer-Policy / CSP (regression introduced with FileResponse).
    """

    @pytest.fixture
    def static_dir(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("<h1>Home</h1>")
        (static / "404.html").write_text("<h1>Not Found</h1>")
        (static / "style.css").write_text("body { color: red; }")
        return static

    @pytest.mark.anyio
    async def test_static_html_gets_security_headers(self, static_dir) -> None:
        from chirp.middleware.static import StaticFiles

        app = App()
        app.add_middleware(SecurityHeadersMiddleware())
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/index.html")
        assert response.status == 200
        assert "text/html" in response.content_type
        assert _header(response, "x-frame-options") == "DENY"
        assert _header(response, "x-content-type-options") == "nosniff"
        assert _header(response, "referrer-policy") == "strict-origin-when-cross-origin"
        assert _header(response, "content-security-policy") is not None

    @pytest.mark.anyio
    async def test_static_css_does_not_get_html_headers(self, static_dir) -> None:
        """Non-HTML static files (CSS) must NOT receive the HTML-only headers."""
        from chirp.middleware.static import StaticFiles

        app = App()
        app.add_middleware(SecurityHeadersMiddleware())
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/style.css")
        assert response.status == 200
        assert _header(response, "x-frame-options") is None

    @pytest.mark.anyio
    async def test_custom_404_html_gets_security_headers(self, static_dir) -> None:
        """The custom 404.html FileResponse must also carry security headers."""
        from chirp.middleware.static import StaticFiles

        app = App()
        app.add_middleware(SecurityHeadersMiddleware())
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/", not_found_page="404.html"))

        async with TestClient(app) as client:
            response = await client.get("/missing-page")
        assert response.status == 404
        assert "text/html" in response.content_type
        assert _header(response, "x-frame-options") == "DENY"
        assert _header(response, "content-security-policy") is not None


class TestStaticFileResponseCSPNonce:
    """CSPNonceMiddleware must also reach static HTML FileResponses."""

    @pytest.fixture
    def static_dir(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("<h1>Home</h1>")
        return static

    @pytest.mark.anyio
    async def test_static_html_gets_csp_nonce(self, static_dir) -> None:
        from chirp.middleware.csp_nonce import CSPNonceMiddleware
        from chirp.middleware.static import StaticFiles

        app = App()
        app.add_middleware(CSPNonceMiddleware())
        app.add_middleware(StaticFiles(directory=static_dir, prefix="/static"))

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/static/index.html")
        assert response.status == 200
        csp = _header(response, "content-security-policy") or ""
        assert "nonce-" in csp

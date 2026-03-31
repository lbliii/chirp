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
    async def test_default_csp_allows_inline_scripts(self) -> None:
        """Inline scripts (dark-mode toggle, Alpine safeData) must run."""
        app = _make_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
        csp = _header(resp, "content-security-policy") or ""
        assert "'unsafe-inline'" in csp

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

"""Tests for SecurityHeadersMiddleware — headers on HTML, skip on non-HTML."""

import pytest

from chirp.app import App
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
    assert (
        _header(response, "strict-transport-security")
        == "max-age=63072000; includeSubDomains"
    )

"""Tests for SecurityHeadersMiddleware — headers on HTML, skip on non-HTML."""

import pytest

from chirp.app import App
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from chirp.testing import TestClient


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
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.anyio
async def test_json_response_skipped() -> None:
    app = _make_app()
    async with TestClient(app) as client:
        response = await client.get("/json")
    assert response.status == 200
    assert response.headers.get("x-frame-options") is None


@pytest.mark.anyio
async def test_custom_config() -> None:
    app = App()
    app.add_middleware(
        SecurityHeadersMiddleware(
            SecurityHeadersConfig(x_frame_options="SAMEORIGIN")
        )
    )

    @app.route("/")
    def index():
        return "Hello"

    async with TestClient(app) as client:
        response = await client.get("/")
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"

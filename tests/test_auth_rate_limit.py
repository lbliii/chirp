"""Tests for auth-focused rate limiting middleware."""

import pytest

from chirp.app import App
from chirp.middleware.auth_rate_limit import AuthRateLimitConfig, AuthRateLimitMiddleware
from chirp.testing import TestClient


@pytest.mark.anyio
async def test_limited_path_blocks_after_threshold() -> None:
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(requests=2, window_seconds=60, block_seconds=120, paths=("/login",))
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-forwarded-for": "1.2.3.4",
        }
        r1 = await client.post("/login", body=b"a=1", headers=headers)
        r2 = await client.post("/login", body=b"a=1", headers=headers)
        r3 = await client.post("/login", body=b"a=1", headers=headers)

    assert r1.status == 200
    assert r2.status == 200
    assert r3.status == 429
    retry_after = r3.header("retry-after")
    assert retry_after is not None


@pytest.mark.anyio
async def test_non_limited_path_is_ignored() -> None:
    app = App()
    app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(paths=("/login",))))

    @app.route("/health", methods=["POST"])
    async def health(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        response = await client.post(
            "/health",
            body=b"a=1",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status == 200


@pytest.mark.anyio
async def test_limit_is_per_identity_key() -> None:
    app = App()
    app.add_middleware(
        AuthRateLimitMiddleware(
            AuthRateLimitConfig(requests=1, window_seconds=60, block_seconds=120, paths=("/login",))
        )
    )

    @app.route("/login", methods=["POST"])
    async def login_route(request):
        _ = await request.form()
        return "ok"

    async with TestClient(app) as client:
        common_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        first_ip_1 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-forwarded-for": "10.0.0.1"},
        )
        second_ip_1 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-forwarded-for": "10.0.0.1"},
        )
        first_ip_2 = await client.post(
            "/login",
            body=b"a=1",
            headers={**common_headers, "x-forwarded-for": "10.0.0.2"},
        )

    assert first_ip_1.status == 200
    assert second_ip_1.status == 429
    assert first_ip_2.status == 200

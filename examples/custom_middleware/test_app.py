"""Tests for the custom middleware example."""

from chirp.testing import TestClient


class TestCustomMiddleware:
    """Verify timing and rate limit middleware."""

    async def test_index_returns_ok(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert response.text == "OK"

    async def test_timing_header_present(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            headers = {k.lower(): v for k, v in response.headers}
            assert "x-response-time" in headers

    async def test_slow_route_has_timing(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/slow")
            assert response.status == 200
            assert response.text == "OK"
            headers = {k.lower(): v for k, v in response.headers}
            assert "x-response-time" in headers
            # Should show ~0.1s or more
            val = headers.get("x-response-time", "")
            assert "s" in val

    async def test_rate_limit_under_limit(self, example_app) -> None:
        async with TestClient(example_app) as client:
            for _ in range(3):
                response = await client.get("/")
                assert response.status == 200

    async def test_rate_limit_exceeded_returns_429(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Exhaust the limit (5 requests per 60s)
            for _ in range(5):
                response = await client.get("/")
                assert response.status == 200
            # 6th request should be 429
            response = await client.get("/")
            assert response.status == 429
            assert "Too Many" in response.text

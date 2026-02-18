"""Tests for CORS middleware."""

from chirp.app import App
from chirp.middleware.builtin import CORSConfig, CORSMiddleware
from chirp.testing import TestClient


def _make_cors_app(config: CORSConfig | None = None) -> App:
    """Helper: create an app with CORS middleware and a simple route."""
    app = App()
    app.add_middleware(CORSMiddleware(config))

    @app.route("/api/data")
    def data():
        return {"message": "hello"}

    @app.route("/api/data", methods=["POST"])
    def create_data():
        return ("created", 201)

    return app


class TestCORSNonCorsRequests:
    """Requests without an Origin header should pass through unaffected."""

    async def test_no_origin_header(self) -> None:
        app = _make_cors_app(CORSConfig(allow_origins=("*",)))
        async with TestClient(app) as client:
            response = await client.get("/api/data")
            assert response.status == 200
            # No CORS headers should be present
            header_names = {name for name, _ in response.headers}
            assert "access-control-allow-origin" not in header_names


class TestCORSSimpleRequests:
    """Simple requests (GET, HEAD, POST with simple headers)."""

    async def test_allowed_origin_gets_cors_headers(self) -> None:
        app = _make_cors_app(CORSConfig(allow_origins=("https://example.com",)))
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://example.com"},
            )
            assert response.status == 200
            assert ("access-control-allow-origin", "https://example.com") in response.headers
            assert ("vary", "Origin") in response.headers

    async def test_disallowed_origin_no_cors_headers(self) -> None:
        app = _make_cors_app(CORSConfig(allow_origins=("https://example.com",)))
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://evil.com"},
            )
            assert response.status == 200
            header_names = {name for name, _ in response.headers}
            assert "access-control-allow-origin" not in header_names

    async def test_wildcard_origin(self) -> None:
        app = _make_cors_app(CORSConfig(allow_origins=("*",)))
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://anything.com"},
            )
            assert ("access-control-allow-origin", "*") in response.headers
            # Wildcard should NOT include Vary header
            assert ("vary", "Origin") not in response.headers


class TestCORSPreflightRequests:
    """Preflight OPTIONS requests."""

    async def test_preflight_returns_204(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_methods=("GET", "POST", "PUT"),
                allow_headers=("Content-Type", "Authorization"),
            )
        )
        async with TestClient(app) as client:
            response = await client.request(
                "OPTIONS",
                "/api/data",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert response.status == 204
            assert ("access-control-allow-origin", "https://example.com") in response.headers
            assert any(name == "access-control-allow-methods" for name, _ in response.headers)
            assert any(name == "access-control-allow-headers" for name, _ in response.headers)

    async def test_preflight_max_age(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("*",),
                max_age=3600,
            )
        )
        async with TestClient(app) as client:
            response = await client.request(
                "OPTIONS",
                "/api/data",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert ("access-control-max-age", "3600") in response.headers


class TestCORSCredentials:
    """Credential support."""

    async def test_credentials_header(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_credentials=True,
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://example.com"},
            )
            assert ("access-control-allow-credentials", "true") in response.headers

    async def test_credentials_with_specific_origin(self) -> None:
        """With credentials=True, the origin must be echoed (not *)."""
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_credentials=True,
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://example.com"},
            )
            assert ("access-control-allow-origin", "https://example.com") in response.headers
            # Should include Vary since it's not wildcard
            assert ("vary", "Origin") in response.headers


class TestCORSExposeHeaders:
    """Expose-Headers support."""

    async def test_expose_headers(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("*",),
                expose_headers=("X-Request-Id", "X-Rate-Limit"),
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://example.com"},
            )
            exposed = response.header("access-control-expose-headers", "")
            assert "X-Request-Id" in exposed
            assert "X-Rate-Limit" in exposed


class TestCORSMultipleOrigins:
    """Multiple allowed origins."""

    async def test_first_origin_allowed(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://a.com", "https://b.com", "https://c.com"),
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://a.com"},
            )
            assert ("access-control-allow-origin", "https://a.com") in response.headers

    async def test_second_origin_allowed(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://a.com", "https://b.com"),
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://b.com"},
            )
            assert ("access-control-allow-origin", "https://b.com") in response.headers

    async def test_unlisted_origin_blocked(self) -> None:
        app = _make_cors_app(
            CORSConfig(
                allow_origins=("https://a.com", "https://b.com"),
            )
        )
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://evil.com"},
            )
            header_names = {name for name, _ in response.headers}
            assert "access-control-allow-origin" not in header_names


class TestCORSDefaults:
    """Default configuration (restrictive)."""

    async def test_default_config_blocks_all_origins(self) -> None:
        """Default CORSConfig has empty allow_origins — nothing is allowed."""
        app = _make_cors_app()  # Default config
        async with TestClient(app) as client:
            response = await client.get(
                "/api/data",
                headers={"Origin": "https://example.com"},
            )
            # Should pass through without CORS headers
            header_names = {name for name, _ in response.headers}
            assert "access-control-allow-origin" not in header_names

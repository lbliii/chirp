"""Tests for CSRF middleware — token generation, validation, and rejection."""

import pytest

from chirp.app import App
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, get_csrf_token
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestCSRFConfig:
    def test_defaults(self) -> None:
        config = CSRFConfig()
        assert config.field_name == "_csrf_token"
        assert config.header_name == "X-CSRF-Token"
        assert config.session_key == "_csrf_token"
        assert config.token_length == 32

    def test_custom_config(self) -> None:
        config = CSRFConfig(field_name="csrf", header_name="X-XSRF", token_length=16)
        assert config.field_name == "csrf"
        assert config.header_name == "X-XSRF"
        assert config.token_length == 16


class TestGetCSRFToken:
    def test_raises_outside_request(self) -> None:
        with pytest.raises(LookupError, match="No CSRF token"):
            get_csrf_token()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def _make_app() -> App:
    """Create a test app with session + CSRF middleware."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(CSRFMiddleware())

    @app.route("/form")
    def form_page():
        token = get_csrf_token()
        return f"token={token}"

    @app.route("/submit", methods=["POST"])
    async def submit(request):
        form = await request.form()
        return f"ok={form.get('data', '')}"

    @app.route("/api/webhook", methods=["POST"])
    async def webhook(request):
        return "webhook-ok"

    return app


def _extract_cookie(response, name: str) -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


class TestCSRFTokenGeneration:
    async def test_token_generated_on_get(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/form")
            assert response.status == 200
            assert response.text.startswith("token=")
            token = response.text.split("=", 1)[1]
            assert len(token) == 64  # 32 bytes hex-encoded

    async def test_token_stable_within_session(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            r1 = await client.get("/form")
            cookie = _extract_cookie(r1, "chirp_session")
            token1 = r1.text.split("=", 1)[1]

            r2 = await client.get("/form", headers={"Cookie": f"chirp_session={cookie}"})
            token2 = r2.text.split("=", 1)[1]

            assert token1 == token2  # Same session → same token


class TestCSRFValidation:
    async def test_post_without_token_rejected(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            # Get session cookie first
            r1 = await client.get("/form")
            cookie = _extract_cookie(r1, "chirp_session")

            # POST without CSRF token
            r2 = await client.post(
                "/submit",
                body=b"data=hello",
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            assert r2.status == 403

    async def test_post_with_form_token_accepted(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            # Get token and session cookie
            r1 = await client.get("/form")
            cookie = _extract_cookie(r1, "chirp_session")
            token = r1.text.split("=", 1)[1]

            # POST with CSRF token in form body
            body = f"_csrf_token={token}&data=hello".encode()
            r2 = await client.post(
                "/submit",
                body=body,
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            assert r2.status == 200
            assert r2.text == "ok=hello"

    async def test_post_with_header_token_accepted(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            # Get token and session cookie
            r1 = await client.get("/form")
            cookie = _extract_cookie(r1, "chirp_session")
            token = r1.text.split("=", 1)[1]

            # POST with CSRF token in header
            r2 = await client.post(
                "/submit",
                body=b"data=hello",
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRF-Token": token,
                },
            )
            assert r2.status == 200
            assert r2.text == "ok=hello"

    async def test_post_with_wrong_token_rejected(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            r1 = await client.get("/form")
            cookie = _extract_cookie(r1, "chirp_session")

            r2 = await client.post(
                "/submit",
                body=b"_csrf_token=wrong-token&data=hello",
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            assert r2.status == 403

    async def test_get_request_not_checked(self) -> None:
        """GET requests should not require CSRF tokens."""
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/form")
            assert response.status == 200


class TestCSRFExemptPaths:
    async def test_exempt_path_skips_validation(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(
            CSRFMiddleware(
                CSRFConfig(
                    exempt_paths=frozenset({"/api/webhook"}),
                )
            )
        )

        @app.route("/api/webhook", methods=["POST"])
        async def webhook(request):
            return "webhook-ok"

        async with TestClient(app) as client:
            # POST to exempt path without token
            response = await client.post(
                "/api/webhook",
                body=b"payload=data",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # Should not get 403 (exempt)
            assert response.status == 200
            assert response.text == "webhook-ok"


class TestCSRFRequiresSession:
    async def test_fails_without_session_middleware(self) -> None:
        """CSRFMiddleware should fail without sessions — returns 500."""
        app = App()
        # Only CSRF middleware, no session middleware
        app.add_middleware(CSRFMiddleware())

        @app.route("/form")
        def form_page():
            return "form"

        async with TestClient(app) as client:
            # GET should fail because CSRF tries to access session
            # The ConfigurationError is caught by the error handler → 500
            response = await client.get("/form")
            assert response.status == 500

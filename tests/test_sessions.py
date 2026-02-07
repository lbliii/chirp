"""Tests for session middleware — signed cookie sessions."""

import pytest

from chirp.app import App
from chirp.errors import ConfigurationError
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.testing import TestClient


class TestSessionConfig:
    def test_default_config(self) -> None:
        config = SessionConfig(secret_key="secret")
        assert config.cookie_name == "chirp_session"
        assert config.max_age == 86400
        assert config.httponly is True
        assert config.samesite == "lax"

    def test_empty_secret_key_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="secret_key must not be empty"):
            SessionMiddleware(SessionConfig(secret_key=""))


class TestSessionMiddlewareInit:
    def test_requires_itsdangerous(self) -> None:
        """SessionMiddleware should raise ConfigurationError if itsdangerous missing.

        We can't actually test the missing-module case without uninstalling,
        but we verify it initializes correctly when present.
        """
        mw = SessionMiddleware(SessionConfig(secret_key="test"))
        assert mw._config.secret_key == "test"


class TestGetSession:
    def test_raises_outside_request(self) -> None:
        with pytest.raises(LookupError, match="No active session"):
            get_session()


class TestSessionBasicOperations:
    async def test_session_set_and_read(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["name"] = "alice"
            return "set"

        @app.route("/get")
        def get_name():
            session = get_session()
            return f"name={session.get('name', 'none')}"

        async with TestClient(app) as client:
            # Set session
            set_resp = await client.get("/set")
            assert set_resp.status == 200

            # Extract session cookie from Set-Cookie header
            cookie_value = _extract_session_cookie(set_resp, "chirp_session")
            assert cookie_value is not None

            # Read session (send cookie back)
            get_resp = await client.get(
                "/get",
                headers={"Cookie": f"chirp_session={cookie_value}"},
            )
            assert get_resp.status == 200
            assert get_resp.text == "name=alice"

    async def test_session_empty_without_cookie(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/check")
        def check():
            session = get_session()
            return f"empty={len(session) == 0}"

        async with TestClient(app) as client:
            response = await client.get("/check")
            assert response.text == "empty=True"

    async def test_session_counter(self) -> None:
        """Session state persists across requests via cookies."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/count")
        def count():
            session = get_session()
            session["visits"] = session.get("visits", 0) + 1
            return f"visits={session['visits']}"

        async with TestClient(app) as client:
            # First visit
            r1 = await client.get("/count")
            assert r1.text == "visits=1"
            cookie = _extract_session_cookie(r1, "chirp_session")

            # Second visit with cookie
            r2 = await client.get("/count", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "visits=2"
            cookie2 = _extract_session_cookie(r2, "chirp_session")

            # Third visit with updated cookie
            r3 = await client.get("/count", headers={"Cookie": f"chirp_session={cookie2}"})
            assert r3.text == "visits=3"


class TestSessionSecurity:
    async def test_tampered_cookie_is_ignored(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/check")
        def check():
            session = get_session()
            return f"empty={len(session) == 0}"

        async with TestClient(app) as client:
            response = await client.get(
                "/check",
                headers={"Cookie": "chirp_session=tampered-value"},
            )
            assert response.text == "empty=True"

    async def test_different_secret_rejects_cookie(self) -> None:
        """A cookie signed with one secret is invalid with another."""
        app1 = App()
        app1.add_middleware(SessionMiddleware(SessionConfig(secret_key="secret-1")))

        @app1.route("/set")
        def set_session():
            session = get_session()
            session["data"] = "from-app1"
            return "set"

        async with TestClient(app1) as client:
            r = await client.get("/set")
            cookie = _extract_session_cookie(r, "chirp_session")

        # Different app with different secret
        app2 = App()
        app2.add_middleware(SessionMiddleware(SessionConfig(secret_key="secret-2")))

        @app2.route("/check")
        def check():
            session = get_session()
            return f"data={session.get('data', 'none')}"

        async with TestClient(app2) as client:
            r = await client.get(
                "/check",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r.text == "data=none"


class TestSessionCookieAttributes:
    async def test_custom_cookie_name(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(
            secret_key="test-secret",
            cookie_name="my_session",
        )))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["x"] = 1
            return "ok"

        async with TestClient(app) as client:
            response = await client.get("/set")
            cookie = _extract_session_cookie(response, "my_session")
            assert cookie is not None


# -- Helpers --


def _extract_session_cookie(response, cookie_name: str) -> str | None:
    """Extract a specific Set-Cookie value from response headers."""
    for name, value in response.headers:
        if name == "set-cookie" and value.startswith(f"{cookie_name}="):
            # Parse "name=value; Path=/; ..."
            cookie_part = value.split(";")[0]
            _, _, cookie_value = cookie_part.partition("=")
            return cookie_value
    return None

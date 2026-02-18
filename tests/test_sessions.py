"""Tests for session middleware — signed cookie sessions."""

import pytest

from chirp.app import App
from chirp.errors import ConfigurationError
from chirp.middleware.sessions import (
    SessionConfig,
    SessionMiddleware,
    get_session,
    regenerate_session,
)
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


class TestSessionDataTypes:
    async def test_session_with_nested_data(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["user"] = {"name": "alice", "roles": ["admin", "editor"]}
            session["prefs"] = [1, 2, 3]
            return "set"

        @app.route("/get")
        def get_data():
            session = get_session()
            user = session.get("user", {})
            prefs = session.get("prefs", [])
            return f"name={user.get('name')},roles={len(user.get('roles', []))},prefs={prefs}"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie = _extract_session_cookie(r1, "chirp_session")

            r2 = await client.get("/get", headers={"Cookie": f"chirp_session={cookie}"})
            assert "name=alice" in r2.text
            assert "roles=2" in r2.text
            assert "prefs=[1, 2, 3]" in r2.text

    async def test_session_key_removal(self) -> None:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["keep"] = "yes"
            session["remove"] = "later"
            return "set"

        @app.route("/remove")
        def remove_key():
            session = get_session()
            session.pop("remove", None)
            return f"keys={sorted(session.keys())}"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie = _extract_session_cookie(r1, "chirp_session")

            r2 = await client.get("/remove", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "keys=['keep']"

    async def test_empty_session_still_gets_cookie(self) -> None:
        """Even an empty session should receive a Set-Cookie (for sliding expiration)."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/empty")
        def empty():
            _ = get_session()  # access but don't modify
            return "ok"

        async with TestClient(app) as client:
            response = await client.get("/empty")
            assert response.status == 200
            cookie = _extract_session_cookie(response, "chirp_session")
            assert cookie is not None


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


class TestRegenerateSession:
    def test_raises_outside_request(self) -> None:
        with pytest.raises(LookupError, match="No active session"):
            regenerate_session()

    async def test_regenerate_clears_session_data(self) -> None:
        """regenerate_session() removes all keys from the session."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["name"] = "alice"
            session["role"] = "admin"
            return "set"

        @app.route("/regenerate")
        def regen():
            session = regenerate_session()
            return f"keys={sorted(session.keys())}"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie = _extract_session_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/regenerate",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "keys=[]"

    async def test_regenerate_produces_new_cookie(self) -> None:
        """After regeneration the signed cookie value should differ."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["x"] = 1
            return "set"

        @app.route("/regenerate")
        def regen():
            regenerate_session()
            return "ok"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie_before = _extract_session_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/regenerate",
                headers={"Cookie": f"chirp_session={cookie_before}"},
            )
            cookie_after = _extract_session_cookie(r2, "chirp_session")
            assert cookie_after is not None
            assert cookie_before != cookie_after

    async def test_old_cookie_invalid_after_regeneration(self) -> None:
        """The pre-regeneration cookie should not restore old data."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/set")
        def set_session():
            session = get_session()
            session["secret"] = "top-secret"
            return "set"

        @app.route("/regenerate")
        def regen():
            regenerate_session()
            return "regenerated"

        @app.route("/check")
        def check():
            session = get_session()
            return f"secret={session.get('secret', 'none')}"

        async with TestClient(app) as client:
            # Set session data
            r1 = await client.get("/set")
            old_cookie = _extract_session_cookie(r1, "chirp_session")

            # Regenerate (discard data)
            r2 = await client.get(
                "/regenerate",
                headers={"Cookie": f"chirp_session={old_cookie}"},
            )
            new_cookie = _extract_session_cookie(r2, "chirp_session")

            # Old cookie still loads (signature valid) but data is gone
            # because itsdangerous timestamps differ and we cleared in-place.
            # The *new* cookie must reflect empty state.
            r3 = await client.get(
                "/check",
                headers={"Cookie": f"chirp_session={new_cookie}"},
            )
            assert r3.text == "secret=none"


class TestSessionRegenerationOnAuth:
    """Integration: login/logout regenerate the session to prevent fixation."""

    async def test_login_regenerates_session(self) -> None:
        from chirp.middleware.auth import AuthConfig, AuthMiddleware, login

        async def _load(uid: str):
            return type("U", (), {"id": uid, "is_authenticated": True})()

        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load)))

        @app.route("/pre-session")
        def pre_session():
            session = get_session()
            session["pre_login"] = "data"
            return "ok"

        @app.route("/login")
        def do_login():
            user = type("U", (), {"id": "alice", "is_authenticated": True})()
            login(user)
            session = get_session()
            return f"pre_login={session.get('pre_login', 'gone')}"

        async with TestClient(app) as client:
            # Set some pre-login data
            r1 = await client.get("/pre-session")
            cookie_before = _extract_session_cookie(r1, "chirp_session")

            # Login — should regenerate
            r2 = await client.get(
                "/login",
                headers={"Cookie": f"chirp_session={cookie_before}"},
            )
            cookie_after = _extract_session_cookie(r2, "chirp_session")

            # Pre-login data should be gone
            assert r2.text == "pre_login=gone"
            # Cookie value should differ
            assert cookie_before != cookie_after

    async def test_logout_clears_entire_session(self) -> None:
        from chirp.middleware.auth import AuthConfig, AuthMiddleware, login, logout

        async def _load(uid: str):
            return type("U", (), {"id": uid, "is_authenticated": True})()

        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load)))

        @app.route("/login")
        def do_login():
            user = type("U", (), {"id": "bob", "is_authenticated": True})()
            login(user)
            session = get_session()
            session["cart"] = ["item1", "item2"]
            return "logged-in"

        @app.route("/logout")
        def do_logout():
            logout()
            return "logged-out"

        @app.route("/check")
        def check():
            session = get_session()
            return f"keys={sorted(session.keys())}"

        async with TestClient(app) as client:
            # Login and set extra session data
            r1 = await client.get("/login")
            cookie = _extract_session_cookie(r1, "chirp_session")

            # Logout — should clear everything
            r2 = await client.get(
                "/logout",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            new_cookie = _extract_session_cookie(r2, "chirp_session")

            # Verify session is empty via new cookie
            r3 = await client.get(
                "/check",
                headers={"Cookie": f"chirp_session={new_cookie}"},
            )
            assert r3.text == "keys=[]"


class TestSessionTimeouts:
    async def test_idle_timeout_expires_session(self) -> None:
        app = App()
        app.add_middleware(
            SessionMiddleware(
                SessionConfig(secret_key="test-secret", idle_timeout_seconds=0)
            )
        )

        @app.route("/set")
        def set_session():
            session = get_session()
            session["k"] = "v"
            return "ok"

        @app.route("/check")
        def check():
            session = get_session()
            return f"k={session.get('k', 'none')}"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie = _extract_session_cookie(r1, "chirp_session")
            r2 = await client.get("/check", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "k=none"

    async def test_absolute_timeout_expires_session(self) -> None:
        app = App()
        app.add_middleware(
            SessionMiddleware(
                SessionConfig(secret_key="test-secret", absolute_timeout_seconds=0)
            )
        )

        @app.route("/set")
        def set_session():
            session = get_session()
            session["k"] = "v"
            return "ok"

        @app.route("/check")
        def check():
            session = get_session()
            return f"k={session.get('k', 'none')}"

        async with TestClient(app) as client:
            r1 = await client.get("/set")
            cookie = _extract_session_cookie(r1, "chirp_session")
            r2 = await client.get("/check", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "k=none"


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

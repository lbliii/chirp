"""Tests for auth middleware — session auth, token auth, dual-mode, login/logout."""

from dataclasses import dataclass

import pytest

from chirp.app import App
from chirp.errors import ConfigurationError
from chirp.middleware.auth import (
    AnonymousUser,
    AuthConfig,
    AuthMiddleware,
    User,
    get_user,
    login,
    logout,
)
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Test user model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeUser:
    """A minimal user model satisfying the User protocol."""

    id: str
    name: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()


# Simulated user database
_USERS: dict[str, FakeUser] = {
    "1": FakeUser(id="1", name="alice"),
    "2": FakeUser(id="2", name="bob", permissions=frozenset({"admin"})),
}

_TOKENS: dict[str, FakeUser] = {
    "tok_alice": _USERS["1"],
    "tok_bob": _USERS["2"],
}


async def _load_user(user_id: str) -> FakeUser | None:
    return _USERS.get(user_id)


async def _verify_token(token: str) -> FakeUser | None:
    return _TOKENS.get(token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_cookie(response, name: str) -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _make_session_app(**auth_kwargs) -> App:
    """Create a test app with session + auth middleware."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(**auth_kwargs)))
    return app


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestAuthConfig:
    def test_defaults(self) -> None:
        config = AuthConfig(load_user=_load_user)
        assert config.session_key == "user_id"
        assert config.token_header == "Authorization"
        assert config.token_scheme == "Bearer"
        assert config.login_url == "/login"
        assert config.exclude_paths == frozenset()

    def test_custom_config(self) -> None:
        config = AuthConfig(
            session_key="uid",
            token_header="X-API-Key",
            token_scheme="Token",
            load_user=_load_user,
            verify_token=_verify_token,
            login_url="/signin",
            exclude_paths=frozenset({"/health"}),
        )
        assert config.session_key == "uid"
        assert config.token_header == "X-API-Key"
        assert config.token_scheme == "Token"
        assert config.login_url == "/signin"
        assert "/health" in config.exclude_paths

    def test_requires_at_least_one_callback(self) -> None:
        with pytest.raises(ConfigurationError, match="at least one"):
            AuthMiddleware(AuthConfig())

    def test_load_user_only(self) -> None:
        mw = AuthMiddleware(AuthConfig(load_user=_load_user))
        assert mw._config.load_user is not None
        assert mw._config.verify_token is None

    def test_verify_token_only(self) -> None:
        mw = AuthMiddleware(AuthConfig(verify_token=_verify_token))
        assert mw._config.verify_token is not None
        assert mw._config.load_user is None


# ---------------------------------------------------------------------------
# AnonymousUser
# ---------------------------------------------------------------------------


class TestAnonymousUser:
    def test_sentinel_values(self) -> None:
        anon = AnonymousUser()
        assert anon.id == ""
        assert anon.is_authenticated is False
        assert anon.permissions == frozenset()

    def test_satisfies_user_protocol(self) -> None:
        anon = AnonymousUser()
        assert isinstance(anon, User)

    def test_frozen(self) -> None:
        anon = AnonymousUser()
        with pytest.raises(AttributeError):
            anon.id = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_user outside request context
# ---------------------------------------------------------------------------


class TestGetUser:
    def test_raises_outside_request(self) -> None:
        with pytest.raises(LookupError, match="No auth context"):
            get_user()


# ---------------------------------------------------------------------------
# Session auth
# ---------------------------------------------------------------------------


class TestAuthMiddlewareSessionAuth:
    async def test_unauthenticated_gets_anonymous(self) -> None:
        app = _make_session_app(load_user=_load_user)

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get("/whoami")
            assert response.status == 200
            assert response.text == "auth=False"

    async def test_session_auth_loads_user(self) -> None:
        app = _make_session_app(load_user=_load_user)

        @app.route("/login")
        def do_login():
            session = get_session()
            session["user_id"] = "1"
            return "logged-in"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id},auth={user.is_authenticated}"

        async with TestClient(app) as client:
            # Login (sets session)
            r1 = await client.get("/login")
            assert r1.status == 200
            cookie = _extract_cookie(r1, "chirp_session")
            assert cookie is not None

            # Access with session cookie
            r2 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.status == 200
            assert r2.text == "id=1,auth=True"

    async def test_session_with_unknown_user_id(self) -> None:
        app = _make_session_app(load_user=_load_user)

        @app.route("/set-bad")
        def set_bad():
            session = get_session()
            session["user_id"] = "999"
            return "set"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            r1 = await client.get("/set-bad")
            cookie = _extract_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "auth=False"


# ---------------------------------------------------------------------------
# Token auth
# ---------------------------------------------------------------------------


class TestAuthMiddlewareTokenAuth:
    async def test_bearer_token_authenticates(self) -> None:
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id},auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get(
                "/whoami",
                headers={"Authorization": "Bearer tok_alice"},
            )
            assert response.status == 200
            assert response.text == "id=1,auth=True"

    async def test_invalid_token_gets_anonymous(self) -> None:
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get(
                "/whoami",
                headers={"Authorization": "Bearer bad_token"},
            )
            assert response.text == "auth=False"

    async def test_missing_token_gets_anonymous(self) -> None:
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get("/whoami")
            assert response.text == "auth=False"

    async def test_wrong_scheme_ignored(self) -> None:
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get(
                "/whoami",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
            )
            assert response.text == "auth=False"

    async def test_empty_token_after_scheme_ignored(self) -> None:
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get(
                "/whoami",
                headers={"Authorization": "Bearer "},
            )
            assert response.text == "auth=False"


# ---------------------------------------------------------------------------
# Dual mode
# ---------------------------------------------------------------------------


class TestAuthMiddlewareDualMode:
    async def test_token_takes_precedence_over_session(self) -> None:
        """When both token and session are present, token wins."""
        app = _make_session_app(load_user=_load_user, verify_token=_verify_token)

        @app.route("/set-session")
        def set_session():
            session = get_session()
            session["user_id"] = "1"  # alice
            return "set"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id}"

        async with TestClient(app) as client:
            # Set session for alice (id=1)
            r1 = await client.get("/set-session")
            cookie = _extract_cookie(r1, "chirp_session")

            # Request with both token (bob) and session cookie (alice)
            r2 = await client.get(
                "/whoami",
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Authorization": "Bearer tok_bob",  # bob (id=2)
                },
            )
            assert r2.text == "id=2"  # Token wins

    async def test_falls_back_to_session_when_no_token(self) -> None:
        app = _make_session_app(load_user=_load_user, verify_token=_verify_token)

        @app.route("/set-session")
        def set_session():
            session = get_session()
            session["user_id"] = "1"
            return "set"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id}"

        async with TestClient(app) as client:
            r1 = await client.get("/set-session")
            cookie = _extract_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "id=1"  # Session fallback


# ---------------------------------------------------------------------------
# Excluded paths
# ---------------------------------------------------------------------------


class TestAuthMiddlewareExcludePaths:
    async def test_excluded_path_gets_anonymous(self) -> None:
        app = _make_session_app(
            load_user=_load_user,
            exclude_paths=frozenset({"/health"}),
        )

        @app.route("/health")
        def health():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get("/health")
            assert response.text == "auth=False"

    async def test_non_excluded_path_authenticates(self) -> None:
        app = _make_session_app(
            load_user=_load_user,
            exclude_paths=frozenset({"/health"}),
        )

        @app.route("/set-session")
        def set_session():
            session = get_session()
            session["user_id"] = "1"
            return "set"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            r1 = await client.get("/set-session")
            cookie = _extract_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "auth=True"


# ---------------------------------------------------------------------------
# Login / Logout helpers
# ---------------------------------------------------------------------------


class TestLoginLogout:
    async def test_login_sets_session_and_context(self) -> None:
        app = _make_session_app(load_user=_load_user)

        @app.route("/do-login")
        def do_login():
            user = _USERS["1"]
            login(user)
            # Verify ContextVar is updated immediately
            current = get_user()
            return f"id={current.id}"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id},auth={user.is_authenticated}"

        async with TestClient(app) as client:
            r1 = await client.get("/do-login")
            assert r1.text == "id=1"
            cookie = _extract_cookie(r1, "chirp_session")

            # Session should persist
            r2 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "id=1,auth=True"

    async def test_logout_clears_session_and_context(self) -> None:
        app = _make_session_app(load_user=_load_user)

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        @app.route("/do-logout")
        def do_logout():
            logout()
            current = get_user()
            return f"auth={current.is_authenticated}"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            # Login
            r1 = await client.get("/do-login")
            cookie = _extract_cookie(r1, "chirp_session")

            # Logout
            r2 = await client.get(
                "/do-logout",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "auth=False"
            cookie2 = _extract_cookie(r2, "chirp_session")

            # Verify session is cleared
            r3 = await client.get(
                "/whoami",
                headers={"Cookie": f"chirp_session={cookie2}"},
            )
            assert r3.text == "auth=False"

    async def test_login_outside_auth_context_raises(self) -> None:
        with pytest.raises(LookupError, match="requires AuthMiddleware"):
            login(_USERS["1"])

    async def test_logout_outside_auth_context_raises(self) -> None:
        with pytest.raises(LookupError, match="requires AuthMiddleware"):
            logout()


# ---------------------------------------------------------------------------
# Requires SessionMiddleware
# ---------------------------------------------------------------------------


class TestAuthRequiresSession:
    async def test_session_auth_without_session_middleware_fails(self) -> None:
        """AuthMiddleware with load_user but no SessionMiddleware → 500."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load_user)))

        @app.route("/whoami")
        def whoami():
            return "ok"

        async with TestClient(app) as client:
            response = await client.get("/whoami")
            # ConfigurationError caught by error handler → 500
            assert response.status == 500

    async def test_token_only_works_without_session(self) -> None:
        """Token-only auth does not require SessionMiddleware."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id},auth={user.is_authenticated}"

        async with TestClient(app) as client:
            response = await client.get(
                "/whoami",
                headers={"Authorization": "Bearer tok_alice"},
            )
            assert response.status == 200
            assert response.text == "id=1,auth=True"

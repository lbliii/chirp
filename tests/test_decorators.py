"""Tests for route protection decorators — @login_required and @requires."""

from dataclasses import dataclass

from chirp.app import App
from chirp.middleware.auth import AuthConfig, AuthMiddleware, get_user, login
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.security.decorators import login_required, requires
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Test user models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeUser:
    """User with permissions."""

    id: str
    name: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class SimpleUser:
    """User without permissions attribute — only id and is_authenticated."""

    id: str
    is_authenticated: bool = True


_USERS: dict[str, FakeUser] = {
    "1": FakeUser(id="1", name="alice"),
    "2": FakeUser(id="2", name="bob", permissions=frozenset({"admin", "editor"})),
    "3": FakeUser(id="3", name="carol", permissions=frozenset({"editor"})),
}

_TOKENS: dict[str, FakeUser] = {
    "tok_alice": _USERS["1"],
    "tok_bob": _USERS["2"],
    "tok_carol": _USERS["3"],
}


async def _load_user(user_id: str) -> FakeUser | None:
    return _USERS.get(user_id)


async def _verify_token(token: str) -> FakeUser | None:
    return _TOKENS.get(token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_cookie(response, name: str) -> str | None:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _get_header(response, name: str) -> str | None:
    for hname, hvalue in response.headers:
        if hname == name:
            return hvalue
    return None


def _make_app() -> App:
    """Create a test app with session + auth + protected routes."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(
        load_user=_load_user,
        verify_token=_verify_token,
    )))

    @app.route("/do-login/{user_id}")
    def do_login(user_id: str):
        user = _USERS[user_id]
        login(user)
        return "ok"

    @app.route("/public")
    def public():
        return "public"

    @app.route("/dashboard")
    @login_required
    async def dashboard():
        user = get_user()
        return f"dashboard:id={user.id}"

    @app.route("/admin")
    @requires("admin")
    async def admin_panel():
        user = get_user()
        return f"admin:id={user.id}"

    @app.route("/editor")
    @requires("editor")
    async def editor_panel():
        user = get_user()
        return f"editor:id={user.id}"

    @app.route("/both")
    @requires("admin", "editor")
    async def both_required():
        user = get_user()
        return f"both:id={user.id}"

    return app


# ---------------------------------------------------------------------------
# @login_required — browser behavior
# ---------------------------------------------------------------------------


class TestLoginRequiredBrowser:
    async def test_unauthenticated_browser_redirects(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/dashboard")
            assert response.status == 302
            location = _get_header(response, "location")
            assert location is not None
            assert "/login" in location
            assert "next=/dashboard" in location

    async def test_authenticated_browser_passes(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            r1 = await client.get("/do-login/1")
            cookie = _extract_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/dashboard",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.status == 200
            assert r2.text == "dashboard:id=1"

    async def test_redirect_preserves_query_string(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/dashboard?tab=settings")
            assert response.status == 302
            location = _get_header(response, "location")
            assert location is not None
            assert "next=/dashboard%3Ftab%3Dsettings" in location or "next=/dashboard?tab=settings" in location


# ---------------------------------------------------------------------------
# @login_required — API behavior
# ---------------------------------------------------------------------------


class TestLoginRequiredAPI:
    async def test_unauthenticated_api_gets_401(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Accept": "application/json"},
            )
            assert response.status == 401

    async def test_authenticated_api_passes(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Authorization": "Bearer tok_alice"},
            )
            assert response.status == 200
            assert response.text == "dashboard:id=1"

    async def test_invalid_token_gets_401(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Authorization": "Bearer bad_token"},
            )
            # Has Authorization header → API request → 401 not redirect
            assert response.status == 401


# ---------------------------------------------------------------------------
# @requires — permission checks
# ---------------------------------------------------------------------------


class TestRequiresPermission:
    async def test_user_with_permission_passes(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/admin",
                headers={"Authorization": "Bearer tok_bob"},
            )
            assert response.status == 200
            assert response.text == "admin:id=2"

    async def test_user_without_permission_gets_403(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            # alice has no permissions
            response = await client.get(
                "/admin",
                headers={"Authorization": "Bearer tok_alice"},
            )
            assert response.status == 403

    async def test_multiple_permissions_required(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            # bob has admin + editor → passes
            r1 = await client.get(
                "/both",
                headers={"Authorization": "Bearer tok_bob"},
            )
            assert r1.status == 200

            # carol has editor only → fails (needs admin too)
            r2 = await client.get(
                "/both",
                headers={"Authorization": "Bearer tok_carol"},
            )
            assert r2.status == 403

    async def test_unauthenticated_gets_401_not_403(self) -> None:
        """Unauthenticated API request to permission-protected route → 401."""
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/admin",
                headers={"Accept": "application/json"},
            )
            assert response.status == 401

    async def test_unauthenticated_browser_redirects(self) -> None:
        """Unauthenticated browser request to permission-protected route → redirect."""
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/admin")
            assert response.status == 302
            location = _get_header(response, "location")
            assert location is not None
            assert "/login" in location


# ---------------------------------------------------------------------------
# Content negotiation
# ---------------------------------------------------------------------------


class TestContentNegotiation:
    async def test_authorization_header_means_api(self) -> None:
        """Presence of Authorization header → API request (401 not redirect)."""
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Authorization": "Bearer bad_token"},
            )
            assert response.status == 401

    async def test_json_accept_means_api(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Accept": "application/json"},
            )
            assert response.status == 401

    async def test_html_accept_means_browser(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get(
                "/dashboard",
                headers={"Accept": "text/html, application/json"},
            )
            # Has both html and json → browser (html present)
            assert response.status == 302

    async def test_no_accept_means_browser(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/dashboard")
            assert response.status == 302


# ---------------------------------------------------------------------------
# @requires with user model that has no permissions
# ---------------------------------------------------------------------------


class TestRequiresNoPermissionsModel:
    async def test_user_without_permissions_attr_gets_403(self) -> None:
        """User model with no permissions attribute → 403."""
        _simple_users: dict[str, SimpleUser] = {
            "tok_simple": SimpleUser(id="s1"),
        }

        async def verify(token: str) -> SimpleUser | None:
            return _simple_users.get(token)

        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=verify)))

        @app.route("/admin")
        @requires("admin")
        async def admin():
            return "admin"

        async with TestClient(app) as client:
            response = await client.get(
                "/admin",
                headers={"Authorization": "Bearer tok_simple"},
            )
            assert response.status == 403


# ---------------------------------------------------------------------------
# Public routes are unaffected
# ---------------------------------------------------------------------------


class TestPublicRoutes:
    async def test_public_routes_accessible(self) -> None:
        app = _make_app()
        async with TestClient(app) as client:
            response = await client.get("/public")
            assert response.status == 200
            assert response.text == "public"


# ---------------------------------------------------------------------------
# Sync handler support — decorators must work with both def and async def
# ---------------------------------------------------------------------------


class TestSyncHandlers:
    """Decorators must handle sync (def) handlers, not just async def."""

    async def test_login_required_sync_handler(self) -> None:
        """@login_required works with a plain def handler."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(
            load_user=_load_user,
            verify_token=_verify_token,
        )))

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        @app.route("/sync-dashboard")
        @login_required
        def sync_dashboard():
            user = get_user()
            return f"sync:id={user.id}"

        async with TestClient(app) as client:
            # Unauthenticated → redirect (decorator runs)
            r1 = await client.get("/sync-dashboard")
            assert r1.status == 302

            # Login
            r2 = await client.get("/do-login")
            cookie = _extract_cookie(r2, "chirp_session")

            # Authenticated → sync handler returns correctly
            r3 = await client.get(
                "/sync-dashboard",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r3.status == 200
            assert r3.text == "sync:id=1"

    async def test_requires_sync_handler(self) -> None:
        """@requires works with a plain def handler."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token)))

        @app.route("/sync-admin")
        @requires("admin")
        def sync_admin():
            user = get_user()
            return f"sync-admin:id={user.id}"

        async with TestClient(app) as client:
            # bob has admin permission
            r1 = await client.get(
                "/sync-admin",
                headers={"Authorization": "Bearer tok_bob"},
            )
            assert r1.status == 200
            assert r1.text == "sync-admin:id=2"

            # alice has no permissions → 403
            r2 = await client.get(
                "/sync-admin",
                headers={"Authorization": "Bearer tok_alice"},
            )
            assert r2.status == 403

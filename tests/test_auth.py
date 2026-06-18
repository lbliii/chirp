"""Tests for auth middleware — session auth, token auth, dual-mode, login/logout."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.errors import ConfigurationError
from chirp.middleware.auth import (
    AnonymousUser,
    AuthConfig,
    AuthMiddleware,
    TokenRevocationStore,
    User,
    get_user,
    login,
    logout,
)
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.security.audit import SecurityEvent, set_security_event_sink
from chirp.testing import TestClient
from tests.helpers.auth import extract_session_cookie

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
            cookie = extract_session_cookie(r1, "chirp_session")
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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

            # Logout
            r2 = await client.get(
                "/do-logout",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.text == "auth=False"
            cookie2 = extract_session_cookie(r2, "chirp_session")

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


class TestSessionVersioning:
    async def test_session_version_mismatch_logs_out_user(self) -> None:
        versions: dict[str, str] = {"1": "v1"}

        def _session_version(user: FakeUser) -> str | None:
            return versions.get(user.id)

        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(
            AuthMiddleware(AuthConfig(load_user=_load_user, session_version=_session_version))
        )

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"auth={user.is_authenticated}"

        async with TestClient(app) as client:
            r1 = await client.get("/do-login")
            cookie = extract_session_cookie(r1, "chirp_session")
            assert cookie is not None

            # Session initially valid.
            r2 = await client.get("/whoami", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "auth=True"

            # Rotate server-side session version => stale session should be rejected.
            versions["1"] = "v2"
            r3 = await client.get("/whoami", headers={"Cookie": f"chirp_session={cookie}"})
            assert r3.text == "auth=False"


# ---------------------------------------------------------------------------
# Permission / policy registries
# ---------------------------------------------------------------------------


class TestAuthRegistries:
    def test_register_permission_raises_after_freeze(self) -> None:
        app = App()
        app.register_permission("admin")  # before freeze: ok
        app.freeze()
        with pytest.raises(RuntimeError):
            app.register_permission("editor")

    def test_register_policy_raises_after_freeze(self) -> None:
        app = App()
        app.register_policy("owner", lambda user, request: True)
        app.freeze()
        with pytest.raises(RuntimeError):
            app.register_policy("late", lambda user, request: True)

    def test_register_policy_rejects_non_callable(self) -> None:
        app = App()
        with pytest.raises(TypeError):
            app.register_policy("bad", "not-callable")  # type: ignore[arg-type]

    def test_registries_thread_into_snapshot(self) -> None:
        from chirp.contracts.checker import _build_snapshot

        app = App(AppConfig(secret_key="x" * 32))
        app.register_permission("admin")
        app.register_policy("owner", lambda user, request: True)
        app.freeze()
        snap = _build_snapshot(app)
        assert "admin" in snap.permission_registry
        assert "owner" in snap.policy_registry


# ---------------------------------------------------------------------------
# Declarative structured-auth enforcement (static META == dynamic meet())
# ---------------------------------------------------------------------------


def _build_auth_pages_tree(tmp_path: Path, *, dynamic: bool) -> Path:
    """A pages tree whose /gated route declares a structured permission gate.

    ``dynamic=False`` -> static ``META`` (an ``AuthSpec``); ``dynamic=True`` ->
    a ``meta()`` callable returning a dict ``auth``. Both must enforce identically
    — that parity is the closed security gap (dynamic meta() auth was dropped).
    """
    pages_dir = tmp_path / "pages"
    (pages_dir / "gated").mkdir(parents=True)
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block content %}{% end %}</body></html>'
    )
    if dynamic:
        meta_body = "def meta():\n    return {'auth': {'permissions': ['admin'], 'mode': 'all'}}\n"
    else:
        meta_body = (
            "from chirp.pages.types import RouteMeta, AuthSpec\n"
            "META = RouteMeta(auth=AuthSpec(permissions=('admin',), mode='all'))\n"
        )
    (pages_dir / "gated" / "_meta.py").write_text(meta_body)
    (pages_dir / "gated" / "page.py").write_text(
        "from chirp import Page\n"
        "def get():\n"
        "    return Page('gated/page.html', 'content', page_block_name='content')\n"
    )
    (pages_dir / "gated" / "page.html").write_text("{% block content %}gated-ok{% end %}")
    return pages_dir


def _auth_pages_app(pages_dir: Path) -> App:
    app = App(AppConfig(template_dir=str(pages_dir)))
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))
    app.mount_pages(str(pages_dir))
    return app


class TestDeclarativeStructuredAuthParity:
    @pytest.mark.parametrize("dynamic", [False, True], ids=["static-META", "dynamic-meta"])
    async def test_missing_permission_denied(self, tmp_path: Path, dynamic: bool) -> None:
        app = _auth_pages_app(_build_auth_pages_tree(tmp_path, dynamic=dynamic))
        async with TestClient(app) as client:
            # tok_alice has no 'admin' permission.
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_alice"})
            assert r.status == 403

    @pytest.mark.parametrize("dynamic", [False, True], ids=["static-META", "dynamic-meta"])
    async def test_permission_allows(self, tmp_path: Path, dynamic: bool) -> None:
        app = _auth_pages_app(_build_auth_pages_tree(tmp_path, dynamic=dynamic))
        async with TestClient(app) as client:
            # tok_bob has the 'admin' permission.
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_bob"})
            assert r.status == 200
            assert "gated-ok" in r.body.decode("utf-8")

    @pytest.mark.parametrize("dynamic", [False, True], ids=["static-META", "dynamic-meta"])
    async def test_unauthenticated_api_401(self, tmp_path: Path, dynamic: bool) -> None:
        app = _auth_pages_app(_build_auth_pages_tree(tmp_path, dynamic=dynamic))
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer bad"})
            assert r.status == 401


# ---------------------------------------------------------------------------
# Named-policy resolution via the policy registry
# ---------------------------------------------------------------------------


def _policy_pages_tree(tmp_path: Path, policy_name: str) -> Path:
    pages_dir = tmp_path / "pages"
    (pages_dir / "secret").mkdir(parents=True)
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block content %}{% end %}</body></html>'
    )
    (pages_dir / "secret" / "_meta.py").write_text(
        "from chirp.pages.types import RouteMeta, AuthSpec\n"
        f"META = RouteMeta(auth=AuthSpec(policy='{policy_name}'))\n"
    )
    (pages_dir / "secret" / "page.py").write_text(
        "from chirp import Page\n"
        "def get():\n"
        "    return Page('secret/page.html', 'content', page_block_name='content')\n"
    )
    (pages_dir / "secret" / "page.html").write_text("{% block content %}secret-ok{% end %}")
    return pages_dir


class TestNamedPolicyResolution:
    async def test_registered_policy_allows(self, tmp_path: Path) -> None:
        pages_dir = _policy_pages_tree(tmp_path, "is_alice")
        app = App(AppConfig(template_dir=str(pages_dir)))
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))
        app.add_middleware(
            AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login"))
        )
        app.register_policy("is_alice", lambda user, request: user.id == "1")
        app.mount_pages(str(pages_dir))

        async with TestClient(app) as client:
            r_ok = await client.get("/secret", headers={"Authorization": "Bearer tok_alice"})
            assert r_ok.status == 200
            r_deny = await client.get("/secret", headers={"Authorization": "Bearer tok_bob"})
            assert r_deny.status == 403

    async def test_unregistered_policy_fails_loud(self, tmp_path: Path) -> None:
        # No app.register_policy("ghost", ...) -> the resolver raises -> 500.
        pages_dir = _policy_pages_tree(tmp_path, "ghost")
        app = App(AppConfig(template_dir=str(pages_dir)))
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))
        app.add_middleware(
            AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login"))
        )
        app.mount_pages(str(pages_dir))

        async with TestClient(app) as client:
            r = await client.get("/secret", headers={"Authorization": "Bearer tok_alice"})
            assert r.status == 500


# ---------------------------------------------------------------------------
# Dict auth coercion — invalid mode fails loud at coercion time
# ---------------------------------------------------------------------------


class TestDictAuthCoercion:
    def test_invalid_mode_raises_value_error(self) -> None:
        """A dict ``auth`` with a mode other than 'all'/'any' fails loud at
        coercion time rather than silently degrading to 'all'."""
        from chirp.pages.discovery import _coerce_auth

        with pytest.raises(ValueError, match="Invalid auth mode 'bogus'"):
            _coerce_auth({"permissions": ["a"], "mode": "bogus"})

    @pytest.mark.parametrize("mode", ["all", "any"])
    def test_valid_modes_coerce(self, mode: str) -> None:
        from chirp.pages.discovery import _coerce_auth
        from chirp.pages.types import AuthSpec

        spec = _coerce_auth({"permissions": ["a"], "mode": mode})
        assert spec == AuthSpec(permissions=("a",), mode=mode)


# ---------------------------------------------------------------------------
# #373 — bearer-path token revocation store (jti + per-user cutoff)
# ---------------------------------------------------------------------------


class _FakeRevocationStore:
    """In-memory revocation store satisfying the TokenRevocationStore Protocol.

    The store owns its own concurrency per the Protocol contract; this fake is
    test-only and single-threaded so a plain dict/set is fine.
    """

    def __init__(
        self,
        revoked_jtis: set[str] | None = None,
        cutoffs: dict[str, int | float] | None = None,
        raise_on_jti: bool = False,
    ) -> None:
        self._revoked_jtis = revoked_jtis or set()
        self._cutoffs = cutoffs or {}
        self._raise_on_jti = raise_on_jti

    async def is_token_revoked(self, jti: str) -> bool:
        if self._raise_on_jti:
            raise RuntimeError("revocation backend down")
        return jti in self._revoked_jtis

    async def user_revoked_at(self, user_id: str) -> int | float | None:
        return self._cutoffs.get(user_id)


# Tokens whose claims encode {jti, sub/user_id, iat}. The app's verify_token
# resolves the user; token_claims surfaces the opaque token's claims.
_REVOC_TOKENS: dict[str, FakeUser] = {
    "tok_alice_jti1": _USERS["1"],
    "tok_bob_jti2": _USERS["2"],
}

_REVOC_CLAIMS: dict[str, dict[str, object]] = {
    "tok_alice_jti1": {"jti": "jti1", "sub": "1", "iat": 1000},
    "tok_bob_jti2": {"jti": "jti2", "sub": "2", "iat": 2000},
}


async def _revoc_verify_token(token: str) -> FakeUser | None:
    return _REVOC_TOKENS.get(token)


def _revoc_claims(token: str) -> dict[str, object]:
    return _REVOC_CLAIMS.get(token, {})


def _revoc_app(store: TokenRevocationStore, with_claims: bool = True) -> App:
    app = App()
    app.add_middleware(
        AuthMiddleware(
            AuthConfig(
                verify_token=_revoc_verify_token,
                token_revocation_store=store,
                token_claims=_revoc_claims if with_claims else None,
            )
        )
    )

    @app.route("/whoami")
    def whoami():
        user = get_user()
        return f"id={user.id},auth={user.is_authenticated}"

    return app


@pytest.fixture
def events() -> list[SecurityEvent]:
    captured: list[SecurityEvent] = []
    set_security_event_sink(captured.append)
    try:
        yield captured
    finally:
        set_security_event_sink(None)


@pytest.mark.issue(373)
class TestTokenRevocationStore:
    async def test_fake_store_satisfies_protocol(self) -> None:
        store = _FakeRevocationStore()
        assert isinstance(store, TokenRevocationStore)

    async def test_revoked_jti_rejected(self, events: list[SecurityEvent]) -> None:
        """Success criterion 1: a revoked jti is rejected on the bearer path."""
        store = _FakeRevocationStore(revoked_jtis={"jti1"})
        async with TestClient(_revoc_app(store)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            # Revoked -> anonymous (no session fallback, no auth.token.invalid).
            assert r.text == "id=,auth=False"
        revoked = [e for e in events if e.name == "auth.token.revoked"]
        assert len(revoked) == 1
        assert revoked[0].user_id == "1"
        assert revoked[0].details == {"reason": "jti", "jti": "jti1"}
        # A revoked (but valid) token must NOT also be flagged invalid.
        assert not any(e.name == "auth.token.invalid" for e in events)

    async def test_unrevoked_token_passes(self, events: list[SecurityEvent]) -> None:
        """Success criterion 1 (negative): an unrevoked token is unaffected."""
        store = _FakeRevocationStore(revoked_jtis={"jti_other"})
        async with TestClient(_revoc_app(store)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            assert r.text == "id=1,auth=True"
        assert not any(e.name == "auth.token.revoked" for e in events)

    async def test_per_user_cutoff_invalidates_pre_cutoff_tokens(
        self, events: list[SecurityEvent]
    ) -> None:
        """Success criterion 2: per-user cutoff invalidates all of a user's
        bearer tokens issued before revoked_at (iat <= revoked_at)."""
        # alice's token iat=1000; cutoff at 1500 -> revoked.
        store = _FakeRevocationStore(cutoffs={"1": 1500})
        async with TestClient(_revoc_app(store)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            assert r.text == "id=,auth=False"
        revoked = [e for e in events if e.name == "auth.token.revoked"]
        assert len(revoked) == 1
        assert revoked[0].user_id == "1"
        assert revoked[0].details == {"reason": "user_cutoff", "iat": 1000, "revoked_at": 1500}

    async def test_cutoff_does_not_affect_post_cutoff_tokens(self) -> None:
        """A token issued after the cutoff (iat > revoked_at) stays valid."""
        # bob's token iat=2000; cutoff at 1500 -> still valid.
        store = _FakeRevocationStore(cutoffs={"2": 1500})
        async with TestClient(_revoc_app(store)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_bob_jti2"})
            assert r.text == "id=2,auth=True"

    async def test_store_unset_is_no_op(self) -> None:
        """Success criterion 3: with no store the bearer path is byte-identical
        to today's behavior (token authenticates normally)."""
        app = App()
        app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_revoc_verify_token)))

        @app.route("/whoami")
        def whoami():
            user = get_user()
            return f"id={user.id},auth={user.is_authenticated}"

        async with TestClient(app) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            assert r.text == "id=1,auth=True"

    async def test_store_error_fails_open(self, events: list[SecurityEvent]) -> None:
        """Locked decision: a store error FAILS OPEN (token treated as not
        revoked) and emits auth.token.revocation_check_error."""
        store = _FakeRevocationStore(revoked_jtis={"jti1"}, raise_on_jti=True)
        async with TestClient(_revoc_app(store)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            # Fail-open: the user still authenticates despite the backend error.
            assert r.text == "id=1,auth=True"
        errors = [e for e in events if e.name == "auth.token.revocation_check_error"]
        assert len(errors) == 1
        assert errors[0].user_id == "1"
        assert errors[0].details == {"error": "RuntimeError"}
        assert not any(e.name == "auth.token.revoked" for e in events)

    async def test_cutoff_skipped_without_claims(self) -> None:
        """Without token_claims the per-user cutoff axis is skipped (no jti/iat
        to evaluate), so the token authenticates normally even with a cutoff."""
        store = _FakeRevocationStore(revoked_jtis={"jti1"}, cutoffs={"1": 1500})
        async with TestClient(_revoc_app(store, with_claims=False)) as client:
            r = await client.get("/whoami", headers={"Authorization": "Bearer tok_alice_jti1"})
            assert r.text == "id=1,auth=True"

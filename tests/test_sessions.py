"""Tests for session middleware — signed cookie sessions."""

import hashlib
from typing import Any, ClassVar

import pytest

from chirp import App, AppConfig
from chirp.errors import ConfigurationError
from chirp.middleware.sessions import (
    CookieSessionStore,
    RedisSessionStore,
    SessionConfig,
    SessionMiddleware,
    get_session,
    regenerate_session,
    resolve_cookie_secure,
)
from chirp.testing import TestClient
from tests.helpers.auth import extract_session_cookie
from tests.helpers.redis_capability import ensure_redis_package


def _set_cookie_header(response: object, cookie_name: str = "chirp_session") -> str | None:
    """Return the full ``Set-Cookie`` header (with attributes) for *cookie_name*."""
    headers = getattr(response, "headers", ())
    for hname, hvalue in headers:
        if hname.lower() == "set-cookie" and hvalue.startswith(f"{cookie_name}="):
            return hvalue
    return None


class _SpySessionStore:
    """Session store spy that records persistence without adding a cookie."""

    def __init__(self, loaded_session: dict[str, Any] | None = None) -> None:
        self.loaded_session = loaded_session or {}
        self.load_calls = 0
        self.save_calls = 0
        self.saved_session: dict[str, Any] | None = None
        self.regenerate_old_id: str | None = None

    async def load(self, request: object) -> dict[str, Any]:
        self.load_calls += 1
        return dict(self.loaded_session)

    async def save(
        self,
        response: Any,
        session: dict[str, Any],
        *,
        regenerate_old_id: str | None = None,
    ) -> Any:
        self.save_calls += 1
        self.saved_session = dict(session)
        self.regenerate_old_id = regenerate_old_id
        return response


class TestSessionConfig:
    def test_default_config(self) -> None:
        config = SessionConfig(secret_key="secret")
        assert config.cookie_name == "chirp_session"
        assert config.max_age == 86400
        assert config.httponly is True
        assert config.samesite == "lax"

    def test_empty_secret_key_raises(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            SessionMiddleware(SessionConfig(secret_key=""))
        msg = str(exc_info.value)
        assert "secret_key must not be empty" in msg
        assert "SessionConfig(secret_key=app.config.secret_key)" in msg
        assert "CHIRP_SECRET_KEY" in msg


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


class TestSessionTemplateGlobal:
    """session() is the template-safe, never-raising session accessor."""

    def test_session_global_never_raises_without_middleware(self) -> None:
        from chirp.middleware.sessions import session

        # Unlike get_session(), the template-safe accessor returns an empty
        # read-only mapping instead of raising LookupError.
        result = session()
        assert result == {}
        assert result.get("anything") is None
        # Read-only: templates cannot accidentally mutate a throwaway dict.
        with pytest.raises(TypeError):
            result["x"] = 1  # type: ignore[index]

    def test_session_global_returns_active_session(self) -> None:
        from chirp.middleware.sessions import _session_var, get_session, session

        active: dict[str, object] = {"flash": "saved"}
        token = _session_var.set(active)
        try:
            assert session() is active
            assert session() is get_session()
        finally:
            _session_var.reset(token)

    def test_session_global_registered_only_with_session_middleware(self) -> None:
        from chirp.middleware.sessions import session as session_global

        # No SessionMiddleware -> session global is NOT registered.
        bare = App()
        bare.freeze()
        assert "session" not in bare._mutable_state.template_globals

        # SessionMiddleware present -> session global harvested via the
        # middleware .template_globals scan in AppCompiler.
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.freeze()
        registered = app._mutable_state.template_globals
        assert registered.get("session") is session_global


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
            cookie_value = extract_session_cookie(set_resp, "chirp_session")
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
            assert _set_cookie_header(response) is None

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
            cookie = extract_session_cookie(r1, "chirp_session")

            # Second visit with cookie
            r2 = await client.get("/count", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "visits=2"
            cookie2 = extract_session_cookie(r2, "chirp_session")

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
            cookie = extract_session_cookie(r, "chirp_session")

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


class TestSessionSigningDigest:
    """SHA-256 signing by default, with SHA-1 backward read."""

    def test_default_digest_is_sha256(self) -> None:
        """Fresh cookies are signed with HMAC-SHA-256 by default."""
        store = CookieSessionStore(SessionConfig(secret_key="test-secret"))
        signer = store._serializer.make_signer()
        assert signer.digest_method is hashlib.sha256

    def test_sha512_digest_opt_in(self) -> None:
        store = CookieSessionStore(SessionConfig(secret_key="test-secret", signer_digest="sha512"))
        signer = store._serializer.make_signer()
        assert signer.digest_method is hashlib.sha512

    def test_bogus_digest_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            CookieSessionStore(SessionConfig(secret_key="test-secret", signer_digest="bogus"))  # type: ignore[arg-type]
        msg = str(exc_info.value)
        assert "signer_digest" in msg
        assert "bogus" in msg

    async def test_backward_read_of_legacy_sha1_cookie(self) -> None:
        """A cookie signed with itsdangerous' historical SHA-1 default still loads."""
        from itsdangerous import URLSafeTimedSerializer

        secret = "test-secret"
        # Emulate a cookie produced by an older release: bare serializer = SHA-1.
        legacy = URLSafeTimedSerializer(secret)
        legacy_cookie = legacy.dumps({"name": "alice"})

        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key=secret)))

        @app.route("/get")
        def get_name():
            session = get_session()
            return f"name={session.get('name', 'none')}"

        async with TestClient(app) as client:
            resp = await client.get(
                "/get",
                headers={"Cookie": f"chirp_session={legacy_cookie}"},
            )
            assert resp.text == "name=alice"


class TestSessionLoadExceptionHandling:
    """``load()`` swallows BadData (fail-safe) but propagates real bugs."""

    async def test_tampered_cookie_yields_empty_session(self) -> None:
        """Tampered/malformed cookies fail safe to an empty session."""
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))

        @app.route("/check")
        def check():
            session = get_session()
            return f"empty={len(session) == 0}"

        async with TestClient(app) as client:
            resp = await client.get(
                "/check",
                headers={"Cookie": "chirp_session=tampered-value"},
            )
            assert resp.text == "empty=True"

    async def test_non_baddata_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A non-BadData error from serializer.loads must NOT be swallowed.

        ``load()`` only reads ``request.cookies`` so a minimal stub suffices to
        drive it to the ``serializer.loads`` call.
        """
        store = CookieSessionStore(SessionConfig(secret_key="test-secret"))

        def boom(*_args: object, **_kwargs: object) -> None:
            raise TypeError("genuine bug, not tamper")

        monkeypatch.setattr(store._serializer, "loads", boom)

        class _StubRequest:
            cookies: ClassVar[dict[str, str]] = {"chirp_session": "anything"}

        with pytest.raises(TypeError, match="genuine bug"):
            await store.load(_StubRequest())  # type: ignore[arg-type]


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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

            r2 = await client.get("/remove", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "keys=['keep']"

    async def test_existing_empty_session_still_gets_cookie(self) -> None:
        """An existing empty session receives Set-Cookie for sliding expiration."""
        secret = "test-secret"
        empty_cookie = CookieSessionStore(SessionConfig(secret_key=secret))._serializer.dumps({})
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key=secret)))

        @app.route("/empty")
        def empty():
            _ = get_session()  # access but don't modify
            return "ok"

        async with TestClient(app) as client:
            response = await client.get(
                "/empty",
                headers={"Cookie": f"chirp_session={empty_cookie}"},
            )
            assert response.status == 200
            cookie = extract_session_cookie(response, "chirp_session")
            assert cookie is not None


@pytest.mark.issue(618)
class TestAnonymousSessionPersistence:
    async def test_anonymous_untouched_get_skips_custom_store_save(self) -> None:
        store = _SpySessionStore()
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret", store=store)))

        @app.route("/public")
        def public():
            return "public"

        async with TestClient(app) as client:
            response = await client.get("/public")

        assert response.status == 200
        assert _set_cookie_header(response) is None
        assert store.load_calls == 1
        assert store.save_calls == 0

    async def test_existing_cookie_preserves_custom_store_refresh(self) -> None:
        store = _SpySessionStore()
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret", store=store)))

        @app.route("/public")
        def public():
            return "public"

        async with TestClient(app) as client:
            response = await client.get(
                "/public",
                headers={"Cookie": "chirp_session=existing"},
            )

        assert response.status == 200
        assert store.save_calls == 1
        assert store.saved_session == {}

    async def test_timeout_metadata_still_persists_new_session(self) -> None:
        store = _SpySessionStore()
        config = SessionConfig(
            secret_key="test-secret",
            idle_timeout_seconds=60,
            store=store,
        )
        app = App()
        app.add_middleware(SessionMiddleware(config))

        @app.route("/public")
        def public():
            return "public"

        async with TestClient(app) as client:
            response = await client.get("/public")

        assert response.status == 200
        assert store.save_calls == 1
        assert store.saved_session is not None
        assert config.created_at_key in store.saved_session
        assert config.last_seen_at_key in store.saved_session

    async def test_regeneration_without_incoming_cookie_still_persists(self) -> None:
        store = _SpySessionStore()
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret", store=store)))

        @app.route("/regenerate")
        def regenerate():
            regenerate_session()
            return "regenerated"

        async with TestClient(app) as client:
            response = await client.get("/regenerate")

        assert response.status == 200
        assert store.save_calls == 1

    async def test_nested_mutation_is_saved_for_existing_session(self) -> None:
        store = _SpySessionStore({"cart": []})
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret", store=store)))

        @app.route("/cart")
        def cart():
            get_session()["cart"].append("item")
            return "updated"

        async with TestClient(app) as client:
            response = await client.get(
                "/cart",
                headers={"Cookie": "chirp_session=existing"},
            )

        assert response.status == 200
        assert store.save_calls == 1
        assert store.saved_session == {"cart": ["item"]}


class TestSessionCookieAttributes:
    async def test_custom_cookie_name(self) -> None:
        app = App()
        app.add_middleware(
            SessionMiddleware(
                SessionConfig(
                    secret_key="test-secret",
                    cookie_name="my_session",
                )
            )
        )

        @app.route("/set")
        def set_session():
            session = get_session()
            session["x"] = 1
            return "ok"

        async with TestClient(app) as client:
            response = await client.get("/set")
            cookie = extract_session_cookie(response, "my_session")
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
            cookie = extract_session_cookie(r1, "chirp_session")

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
            cookie_before = extract_session_cookie(r1, "chirp_session")

            r2 = await client.get(
                "/regenerate",
                headers={"Cookie": f"chirp_session={cookie_before}"},
            )
            cookie_after = extract_session_cookie(r2, "chirp_session")
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
            old_cookie = extract_session_cookie(r1, "chirp_session")

            # Regenerate (discard data)
            r2 = await client.get(
                "/regenerate",
                headers={"Cookie": f"chirp_session={old_cookie}"},
            )
            new_cookie = extract_session_cookie(r2, "chirp_session")

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
            cookie_before = extract_session_cookie(r1, "chirp_session")

            # Login — should regenerate
            r2 = await client.get(
                "/login",
                headers={"Cookie": f"chirp_session={cookie_before}"},
            )
            cookie_after = extract_session_cookie(r2, "chirp_session")

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
            cookie = extract_session_cookie(r1, "chirp_session")

            # Logout — should clear everything
            r2 = await client.get(
                "/logout",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            new_cookie = extract_session_cookie(r2, "chirp_session")

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
            SessionMiddleware(SessionConfig(secret_key="test-secret", idle_timeout_seconds=0))
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
            cookie = extract_session_cookie(r1, "chirp_session")
            r2 = await client.get("/check", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "k=none"

    async def test_absolute_timeout_expires_session(self) -> None:
        app = App()
        app.add_middleware(
            SessionMiddleware(SessionConfig(secret_key="test-secret", absolute_timeout_seconds=0))
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
            cookie = extract_session_cookie(r1, "chirp_session")
            r2 = await client.get("/check", headers={"Cookie": f"chirp_session={cookie}"})
            assert r2.text == "k=none"


class TestResolveCookieSecure:
    """The ``secure="auto"`` resolver: env is the sole posture signal."""

    def test_auto_production_is_true(self) -> None:
        assert resolve_cookie_secure("auto", env="production") is True

    def test_auto_staging_is_true(self) -> None:
        assert resolve_cookie_secure("auto", env="staging") is True

    def test_auto_development_is_false(self) -> None:
        assert resolve_cookie_secure("auto", env="development") is False

    def test_auto_unknown_env_is_false(self) -> None:
        """An unrecognized env is treated as non-secure (fail safe to dev)."""
        assert resolve_cookie_secure("auto", env="local") is False

    def test_explicit_true_passes_through(self) -> None:
        # Explicit opt-in is honored even in development.
        assert resolve_cookie_secure(True, env="development") is True

    def test_explicit_false_passes_through(self) -> None:
        # Explicit opt-out is honored even in production.
        assert resolve_cookie_secure(False, env="production") is False

    def test_config_default_secure_is_auto(self) -> None:
        assert SessionConfig(secret_key="s").secure == "auto"


class TestSessionSecureResolutionAtFreeze:
    """Freeze resolves ``secure="auto"`` to a concrete bool by ``config.env``.

    Regression guard: ``ssl_certfile`` set in *development* must NOT promote
    secure to True (the dropped clause that would silently log local-HTTPS dev
    users out). env is the only signal.
    """

    def test_production_default_emits_secure_cookie(self) -> None:
        app = App(config=AppConfig(secret_key="s", env="production", debug=False))
        mw = SessionMiddleware(SessionConfig(secret_key="s"))
        app.add_middleware(mw)
        app.freeze()
        assert mw.secure is True

    def test_development_default_is_not_secure(self) -> None:
        app = App(config=AppConfig(secret_key="s", env="development", debug=True))
        mw = SessionMiddleware(SessionConfig(secret_key="s"))
        app.add_middleware(mw)
        app.freeze()
        assert mw.secure is False

    def test_development_with_ssl_certfile_stays_not_secure(self) -> None:
        """ssl_certfile in dev (local HTTPS) must NOT force Secure cookies."""
        app = App(
            config=AppConfig(
                secret_key="s",
                env="development",
                debug=True,
                ssl_certfile="cert.pem",
            )
        )
        mw = SessionMiddleware(SessionConfig(secret_key="s"))
        app.add_middleware(mw)
        app.freeze()
        assert mw.secure is False

    def test_explicit_false_not_promoted_in_production(self) -> None:
        app = App(config=AppConfig(secret_key="s", env="production", debug=False))
        mw = SessionMiddleware(SessionConfig(secret_key="s", secure=False))
        app.add_middleware(mw)
        app.freeze()
        assert mw.secure is False

    def test_store_config_never_holds_auto_after_freeze(self) -> None:
        """The store's cached config must hold a bool (with_cookie is typed bool)."""
        app = App(config=AppConfig(secret_key="s", env="production", debug=False))
        mw = SessionMiddleware(SessionConfig(secret_key="s"))
        app.add_middleware(mw)
        app.freeze()
        assert mw._store._config.secure is True
        assert mw._config.secure is True


class TestSessionSecureEndToEnd:
    """The resolved value is actually emitted on the Set-Cookie header."""

    async def test_production_sets_secure_attribute(self) -> None:
        app = App(config=AppConfig(secret_key="s", env="production", debug=False))
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="s")))

        @app.route("/set")
        def set_session():
            get_session()["k"] = "v"
            return "ok"

        async with TestClient(app) as client:
            r = await client.get("/set")
            header = _set_cookie_header(r)
            assert header is not None
            assert "Secure" in header.split("; ")

    async def test_development_omits_secure_attribute(self) -> None:
        app = App(config=AppConfig(secret_key="s", env="development", debug=False))
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="s")))

        @app.route("/set")
        def set_session():
            get_session()["k"] = "v"
            return "ok"

        async with TestClient(app) as client:
            r = await client.get("/set")
            header = _set_cookie_header(r)
            assert header is not None
            assert "Secure" not in header.split("; ")


@pytest.mark.issue(906)
class TestRedisStoreSecureResolution:
    """RedisSessionStore honors the resolved secure value (no real Redis needed).

    Local installs without chirp[redis] skip; the redis-capability CI lane
    sets CHIRP_REQUIRE_REDIS=1 so absence fails instead of skipping (#906).
    """

    @pytest.fixture(autouse=True)
    def _require_redis(self) -> None:
        ensure_redis_package()

    def test_redis_store_resolve_secure_auto_production(self) -> None:
        store = RedisSessionStore(SessionConfig(secret_key="s", secure="auto"), "redis://localhost")
        store.resolve_secure("production")
        assert store._config.secure is True

    def test_redis_store_resolve_secure_auto_development(self) -> None:
        store = RedisSessionStore(SessionConfig(secret_key="s", secure="auto"), "redis://localhost")
        store.resolve_secure("development")
        assert store._config.secure is False

    def test_two_config_pattern_resolves_inner_store_config(self) -> None:
        """A user-supplied store carries its OWN inner config that must resolve.

        The save() path reads the *store's* config for cookie attributes, so the
        inner SessionConfig — not just the outer one — must be resolved at freeze.
        """
        inner = SessionConfig(secret_key="inner", secure="auto")
        store = RedisSessionStore(inner, "redis://localhost")
        outer = SessionConfig(secret_key="outer", secure="auto", store=store)
        app = App(config=AppConfig(secret_key="s", env="production", debug=False))
        mw = SessionMiddleware(outer)
        app.add_middleware(mw)
        app.freeze()
        # The store's inner config (authoritative for cookie attrs) is resolved...
        assert store._config.secure is True
        # ...and the middleware's effective `secure` reads the store's config.
        assert mw.secure is True

    def test_two_config_pattern_development_stays_false(self) -> None:
        inner = SessionConfig(secret_key="inner", secure="auto")
        store = RedisSessionStore(inner, "redis://localhost")
        outer = SessionConfig(secret_key="outer", secure="auto", store=store)
        app = App(config=AppConfig(secret_key="s", env="development", debug=True))
        mw = SessionMiddleware(outer)
        app.add_middleware(mw)
        app.freeze()
        assert store._config.secure is False
        assert mw.secure is False

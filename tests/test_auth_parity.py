"""Parity tests for the shared authenticate-or-deny core.

The #1 risk in unifying the declarative ``RouteMeta.auth`` gate with the
imperative ``@login_required`` / ``@requires`` decorators is audit-event drift:
downstream SIEM keys off ``emit_security_event`` ``name`` + ``details``, and the
two paths historically emitted DIFFERENT shapes. These tests lock the ONE
canonical payload and assert BOTH paths produce it identically.

They also cover:

- :func:`normalize_auth_spec` back-compat for every string form;
- the shared core's ``all`` / ``any`` permission matching and authn-only mode;
- str ``RouteMeta.auth`` 302/401/403 outcomes (unchanged).
"""

from dataclasses import dataclass

import pytest

from chirp import App
from chirp.middleware.auth import (
    AuthConfig,
    AuthMiddleware,
    UserWithPermissions,
    _active_config,
    _user_var,
)
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.pages.auth_gate import enforce_route_meta_auth
from chirp.pages.types import AuthSpec, RouteMeta
from chirp.security.audit import SecurityEvent, set_security_event_sink
from chirp.security.auth_core import enforce_auth, normalize_auth_spec
from chirp.security.decorators import requires
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PermUser:
    id: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PlainUser:
    """No permissions attribute -> does not satisfy UserWithPermissions."""

    id: str
    is_authenticated: bool = True


@dataclass(frozen=True, slots=True)
class Anon:
    id: str = ""
    is_authenticated: bool = False
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ScopeClient:
    """Machine client carrying token scopes but NO human permissions.

    Satisfies ClientWithScopes (has ``scopes``) but NOT UserWithPermissions
    (no ``permissions``) — proving the two axes are independent.
    """

    id: str
    is_authenticated: bool = True
    scopes: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# normalize_auth_spec — exact back-compat
# ---------------------------------------------------------------------------


class TestNormalizeAuthSpec:
    @pytest.mark.parametrize("value", [None, "", "none", "optional"])
    def test_open_values_normalize_to_none(self, value) -> None:
        assert normalize_auth_spec(value) is None

    def test_required_is_authn_only(self) -> None:
        spec = normalize_auth_spec("required")
        assert spec == AuthSpec(permissions=(), mode="all", policy=None)

    def test_arbitrary_string_is_single_permission(self) -> None:
        spec = normalize_auth_spec("admin")
        assert spec == AuthSpec(permissions=("admin",), mode="all")

    def test_authspec_passes_through(self) -> None:
        spec = AuthSpec(permissions=("a", "b"), mode="any", policy="p")
        assert normalize_auth_spec(spec) is spec

    def test_case_sensitive_like_legacy(self) -> None:
        # "None"/"Required" were ALWAYS treated as permission names, not tokens
        # (the historical gate is case-sensitive). Preserve that exactly.
        assert normalize_auth_spec("None") == AuthSpec(permissions=("None",))
        assert normalize_auth_spec("Required") == AuthSpec(permissions=("Required",))


# ---------------------------------------------------------------------------
# Shared core — permission matching (all / any / authn-only)
# ---------------------------------------------------------------------------


def _run_in_auth_context(user, coro_factory):
    """Run an async core call with the user ContextVar set (no full request)."""
    import anyio

    async def runner():
        tok = _user_var.set(user)
        cfg_tok = _active_config.set(None)
        try:
            return await coro_factory()
        finally:
            _user_var.reset(tok)
            _active_config.reset(cfg_tok)

    return anyio.run(runner)


class _FakeRequest:
    """Minimal request: API-style (Authorization header) to force 401 path."""

    def __init__(self, api: bool = True) -> None:
        self.path = "/x"
        self.method = "GET"
        self.url = "/x"
        self.headers = {"authorization": "Bearer t"} if api else {"accept": "text/html"}


class TestSharedCorePermissions:
    def test_mode_all_requires_subset(self) -> None:
        from chirp.errors import HTTPError

        user = PermUser(id="u", permissions=frozenset({"a"}))
        spec = AuthSpec(permissions=("a", "b"), mode="all")
        with pytest.raises(HTTPError) as exc:
            _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))
        assert exc.value.status == 403

    def test_mode_all_passes_with_full_set(self) -> None:
        user = PermUser(id="u", permissions=frozenset({"a", "b", "c"}))
        spec = AuthSpec(permissions=("a", "b"), mode="all")
        # No raise == allowed.
        _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))

    def test_mode_any_passes_on_intersection(self) -> None:
        user = PermUser(id="u", permissions=frozenset({"b"}))
        spec = AuthSpec(permissions=("a", "b"), mode="any")
        _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))

    def test_mode_any_denies_on_empty_intersection(self) -> None:
        from chirp.errors import HTTPError

        user = PermUser(id="u", permissions=frozenset({"z"}))
        spec = AuthSpec(permissions=("a", "b"), mode="any")
        with pytest.raises(HTTPError) as exc:
            _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))
        assert exc.value.status == 403

    def test_authn_only_passes_for_any_authenticated_user(self) -> None:
        user = PlainUser(id="u")  # no permissions attr — authn-only must not care
        spec = AuthSpec()
        _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))

    def test_unauthenticated_api_raises_401(self) -> None:
        from chirp.errors import HTTPError

        user = Anon()
        spec = AuthSpec()
        with pytest.raises(HTTPError) as exc:
            _run_in_auth_context(user, lambda: enforce_auth(spec, _FakeRequest(), user))
        assert exc.value.status == 401

    def test_user_protocol_check(self) -> None:
        # Sanity: PermUser satisfies UserWithPermissions; PlainUser does not.
        assert isinstance(PermUser(id="u"), UserWithPermissions)
        assert not isinstance(PlainUser(id="u"), UserWithPermissions)


# ---------------------------------------------------------------------------
# AUDIT-EVENT PARITY LOCK — the #1 risk
# ---------------------------------------------------------------------------
#
# Canonical payloads (documented in src/chirp/security/AGENTS.md):
#   unauthenticated   -> name="auth.require.unauthenticated"
#   permission-denied -> name="authz.permission.denied", details={"missing": sorted([...])}
#   missing-protocol  -> name="authz.permission.denied",
#                        details={"reason": "missing_permissions_protocol", "missing": [...]}
#   policy-denied     -> name="authz.policy.denied", details={"policy": <name>}
#
# Both the @requires path and the declarative RouteMeta.auth path MUST emit
# byte-for-byte identical name+details for the same outcome.


def _decorator_app() -> App:
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(
        AuthMiddleware(
            AuthConfig(
                verify_token=_verify_token,
                login_url="/login",
            )
        )
    )

    @app.route("/needs-admin")
    @requires("admin")
    def needs_admin():
        return "ok"

    return app


def _declarative_app() -> App:
    """An app whose route runs the DECLARATIVE gate inline, mirroring how
    ``app/registry.py`` awaits ``enforce_route_meta_auth`` per mounted page."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(
        AuthMiddleware(
            AuthConfig(
                verify_token=_verify_token,
                login_url="/login",
            )
        )
    )

    @app.route("/needs-admin")
    async def needs_admin(request):
        await enforce_route_meta_auth(RouteMeta(auth="admin"), request)
        return "ok"

    return app


def is_owner(user, request) -> bool:
    """A policy that always denies — used to exercise the policy-denied event.

    Its ``__name__`` is ``is_owner``; both gate paths reference the policy under
    that exact identifier so their ``authz.policy.denied`` payloads match.
    """
    return False


def _policy_decorator_app() -> App:
    """Imperative path: ``@requires(policy=is_owner)`` names the policy by
    ``is_owner.__name__`` == ``"is_owner"``."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))

    @app.route("/needs-owner")
    @requires(policy=is_owner)
    def needs_owner():
        return "ok"

    return app


def _policy_declarative_app() -> App:
    """Declarative path: ``AuthSpec(policy="is_owner")`` resolved against a
    registered policy named ``"is_owner"`` (== the callable's ``__name__``)."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))

    def _resolver(name: str):
        return is_owner if name == "is_owner" else None

    @app.route("/needs-owner")
    async def needs_owner(request):
        await enforce_route_meta_auth(
            RouteMeta(auth=AuthSpec(policy="is_owner")), request, policy_resolver=_resolver
        )
        return "ok"

    return app


def _scope_declarative_app(scopes: tuple[str, ...], mode: str = "all") -> App:
    """Declarative path: ``AuthSpec(scopes=...)`` enforced inline, mirroring the
    page wrapper. Scopes gate the machine-auth axis via the shared core."""
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))

    @app.route("/needs-scope")
    async def needs_scope(request):
        await enforce_route_meta_auth(RouteMeta(auth=AuthSpec(scopes=scopes, mode=mode)), request)
        return "ok"

    return app


_PARITY_USERS = {
    "tok_admin": PermUser(id="a", permissions=frozenset({"admin"})),
    "tok_plain_perm": PermUser(id="p", permissions=frozenset({"viewer"})),
    # Machine clients: scopes, no permissions.
    "tok_scope_write": ScopeClient(id="mw", scopes=frozenset({"webhook:write"})),
    "tok_scope_read": ScopeClient(id="mr", scopes=frozenset({"webhook:read"})),
}


async def _verify_token(token: str):
    return _PARITY_USERS.get(token)


def _captured_event(events: list[SecurityEvent], name: str) -> SecurityEvent | None:
    for e in events:
        if e.name == name:
            return e
    return None


class TestAuditEventParity:
    @pytest.fixture(autouse=True)
    def events_sink(self):
        events: list[SecurityEvent] = []
        set_security_event_sink(events.append)
        try:
            yield events
        finally:
            set_security_event_sink(None)

    async def _emit_for(self, app: App, headers: dict[str, str], path: str = "/needs-admin"):
        async with TestClient(app) as client:
            await client.get(path, headers=headers)

    async def test_unauthenticated_parity(self, events_sink) -> None:
        # API request (Authorization header forces the 401/event branch).
        await self._emit_for(_decorator_app(), {"Authorization": "Bearer bad"})
        dec = _captured_event(events_sink, "auth.require.unauthenticated")
        events_sink.clear()
        await self._emit_for(_declarative_app(), {"Authorization": "Bearer bad"})
        decl = _captured_event(events_sink, "auth.require.unauthenticated")
        assert dec is not None
        assert decl is not None
        assert dec.name == decl.name == "auth.require.unauthenticated"
        assert dec.details == decl.details == {}

    async def test_permission_denied_parity(self, events_sink) -> None:
        # Authenticated user lacking the 'admin' permission.
        await self._emit_for(_decorator_app(), {"Authorization": "Bearer tok_plain_perm"})
        dec = _captured_event(events_sink, "authz.permission.denied")
        events_sink.clear()
        await self._emit_for(_declarative_app(), {"Authorization": "Bearer tok_plain_perm"})
        decl = _captured_event(events_sink, "authz.permission.denied")
        assert dec is not None
        assert decl is not None
        # Canonical permission-denied payload.
        assert dec.name == decl.name == "authz.permission.denied"
        assert dec.details == decl.details == {"missing": ["admin"]}

    async def test_missing_protocol_parity(self, events_sink) -> None:
        # User WITHOUT a permissions attribute hitting a permission gate.
        _PARITY_USERS["tok_noperm"] = PlainUser(id="np")  # type: ignore[assignment]
        try:
            await self._emit_for(_decorator_app(), {"Authorization": "Bearer tok_noperm"})
            dec = _captured_event(events_sink, "authz.permission.denied")
            events_sink.clear()
            await self._emit_for(_declarative_app(), {"Authorization": "Bearer tok_noperm"})
            decl = _captured_event(events_sink, "authz.permission.denied")
        finally:
            _PARITY_USERS.pop("tok_noperm", None)
        assert dec is not None
        assert decl is not None
        assert dec.name == decl.name == "authz.permission.denied"
        expected = {"reason": "missing_permissions_protocol", "missing": ["admin"]}
        assert dec.details == expected
        assert decl.details == expected

    async def test_permission_granted_emits_nothing(self, events_sink) -> None:
        await self._emit_for(_decorator_app(), {"Authorization": "Bearer tok_admin"})
        assert _captured_event(events_sink, "authz.permission.denied") is None

    async def test_policy_denied_parity(self, events_sink) -> None:
        """A RESOLVED policy that returns falsy emits authz.policy.denied with
        BYTE-IDENTICAL name + details on both gate paths.

        The ``policy`` detail value is the policy IDENTIFIER as referenced: the
        REGISTERED NAME for declarative ``AuthSpec(policy="is_owner")`` and the
        function ``__name__`` for ``@requires(policy=is_owner)``. To make them
        match we register the policy under a name EQUAL to the callable's
        ``__name__`` (``is_owner``).
        """
        await self._emit_for(
            _policy_decorator_app(), {"Authorization": "Bearer tok_admin"}, path="/needs-owner"
        )
        dec = _captured_event(events_sink, "authz.policy.denied")
        events_sink.clear()
        await self._emit_for(
            _policy_declarative_app(), {"Authorization": "Bearer tok_admin"}, path="/needs-owner"
        )
        decl = _captured_event(events_sink, "authz.policy.denied")
        assert dec is not None
        assert decl is not None
        # Byte-identical canonical policy-denied payload (name + details).
        assert dec.name == decl.name == "authz.policy.denied"
        assert dec.details == decl.details == {"policy": "is_owner"}

    async def test_policy_denied_status_403(self) -> None:
        """A resolved policy returning falsy is a real denial -> 403 on both paths."""
        async with TestClient(_policy_decorator_app()) as client:
            r = await client.get("/needs-owner", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 403
        async with TestClient(_policy_declarative_app()) as client:
            r = await client.get("/needs-owner", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 403

    async def test_scope_denied_payload_lock(self, events_sink) -> None:
        """A declared scope the client lacks emits the canonical authz.scope.denied
        payload: name='authz.scope.denied', details={'missing': sorted([...])}.

        The machine-auth axis is distinct from authz.permission.denied so SIEM
        can separate machine-token denials from human-permission denials. The
        shared core (used by both gate paths) is the single producer, so locking
        the payload here keeps the event from drifting.
        """
        await self._emit_for(
            _scope_declarative_app(("webhook:write",)),
            {"Authorization": "Bearer tok_scope_read"},
            path="/needs-scope",
        )
        evt = _captured_event(events_sink, "authz.scope.denied")
        assert evt is not None
        assert evt.name == "authz.scope.denied"
        assert evt.details == {"missing": ["webhook:write"]}

    async def test_scope_missing_protocol_payload_lock(self, events_sink) -> None:
        """A client with no scopes attribute hitting a scope gate emits the
        missing-scopes-protocol shape."""
        await self._emit_for(
            _scope_declarative_app(("webhook:write",)),
            {"Authorization": "Bearer tok_admin"},  # PermUser: no scopes attr
            path="/needs-scope",
        )
        evt = _captured_event(events_sink, "authz.scope.denied")
        assert evt is not None
        assert evt.details == {
            "reason": "missing_scopes_protocol",
            "missing": ["webhook:write"],
        }

    async def test_scope_granted_emits_nothing(self, events_sink) -> None:
        await self._emit_for(
            _scope_declarative_app(("webhook:write",)),
            {"Authorization": "Bearer tok_scope_write"},
            path="/needs-scope",
        )
        assert _captured_event(events_sink, "authz.scope.denied") is None


# ---------------------------------------------------------------------------
# String RouteMeta.auth end-to-end outcomes (back-compat — unchanged 302/401/403)
# ---------------------------------------------------------------------------


def _declarative_outcome_app(auth_value) -> App:
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="parity-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))

    @app.route("/gated")
    async def gated(request):
        await enforce_route_meta_auth(RouteMeta(auth=auth_value), request)
        return "ok"

    return app


class TestStringAuthOutcomes:
    @pytest.mark.parametrize("token_open_value", [None, "none", "optional", ""])
    async def test_open_values_allow_anonymous(self, token_open_value) -> None:
        app = _declarative_outcome_app(token_open_value)
        async with TestClient(app) as client:
            r = await client.get("/gated")
            assert r.status == 200
            assert r.text == "ok"

    async def test_required_browser_redirects(self) -> None:
        app = _declarative_outcome_app("required")
        async with TestClient(app) as client:
            r = await client.get("/gated")
            assert r.status == 302
            assert any(n == "location" and "/login" in v for n, v in r.headers)

    async def test_required_api_401(self) -> None:
        app = _declarative_outcome_app("required")
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer bad"})
            assert r.status == 401

    async def test_required_authenticated_passes(self) -> None:
        app = _declarative_outcome_app("required")
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 200

    async def test_permission_string_denies_without_it(self) -> None:
        app = _declarative_outcome_app("admin")
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_plain_perm"})
            assert r.status == 403

    async def test_permission_string_allows_with_it(self) -> None:
        app = _declarative_outcome_app("admin")
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 200

    async def test_authspec_all_mode_enforced(self) -> None:
        app = _declarative_outcome_app(AuthSpec(permissions=("admin", "editor"), mode="all"))
        async with TestClient(app) as client:
            # tok_admin has only 'admin' -> missing 'editor' -> 403
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 403

    async def test_authspec_any_mode_enforced(self) -> None:
        app = _declarative_outcome_app(AuthSpec(permissions=("admin", "editor"), mode="any"))
        async with TestClient(app) as client:
            r = await client.get("/gated", headers={"Authorization": "Bearer tok_admin"})
            assert r.status == 200

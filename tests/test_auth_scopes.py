"""Machine-auth scope axis on ``AuthSpec`` (issue #375).

A scope gate lets webhook / cron / provisioning endpoints gate on a
token-resolved client's *scopes* independently of human permissions:

- a token client holding the scope but NO permissions passes;
- a human user holding the permissions but NOT the scope fails the scope gate;
- scope enforcement is implicitly OFF when no ``AuthSpec`` declares scopes;
- scope-name equality is compared in constant time (``secrets.compare_digest``).
"""

from dataclasses import dataclass

import pytest

from chirp import App
from chirp.errors import HTTPError
from chirp.middleware.auth import (
    AuthConfig,
    AuthMiddleware,
    ClientWithScopes,
    MachineClient,
    UserWithPermissions,
    _active_config,
    _user_var,
)
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.pages.auth_gate import enforce_route_meta_auth
from chirp.pages.discovery import _coerce_auth, dict_to_route_meta
from chirp.pages.types import AuthSpec, RouteMeta
from chirp.security.auth_core import enforce_auth
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Test identities — the two axes are deliberately disjoint.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MachineCaller:
    """Has scopes, NO permissions → ClientWithScopes but not UserWithPermissions."""

    id: str
    is_authenticated: bool = True
    scopes: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class HumanUser:
    """Has permissions, NO scopes → UserWithPermissions but not ClientWithScopes."""

    id: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Anon:
    id: str = ""
    is_authenticated: bool = False
    scopes: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Protocol sanity
# ---------------------------------------------------------------------------


def test_protocols_are_independent() -> None:
    machine = MachineCaller(id="m", scopes=frozenset({"webhook:write"}))
    human = HumanUser(id="h", permissions=frozenset({"admin"}))
    # Machine client satisfies the scope protocol but not the permission one.
    assert isinstance(machine, ClientWithScopes)
    assert isinstance(machine, MachineClient)  # alias
    assert not isinstance(machine, UserWithPermissions)
    # Human user satisfies the permission protocol but not the scope one.
    assert isinstance(human, UserWithPermissions)
    assert not isinstance(human, ClientWithScopes)


def test_authspec_scopes_is_frozen_serializable() -> None:
    spec = AuthSpec(scopes=("webhook:write", "webhook:read"), mode="any")
    assert spec.scopes == ("webhook:write", "webhook:read")
    # Frozen dataclass: assignment raises.
    with pytest.raises(Exception):  # noqa: B017,PT011 — FrozenInstanceError
        spec.scopes = ()  # type: ignore[misc]
    # Default is empty (no scope gate).
    assert AuthSpec().scopes == ()


# ---------------------------------------------------------------------------
# Shared-core scope step (direct enforce_auth)
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self) -> None:
        self.path = "/x"
        self.method = "POST"
        self.url = "/x"
        self.headers = {"authorization": "Bearer t"}


def _run(user, spec) -> None:
    import anyio

    async def runner():
        tok = _user_var.set(user)
        cfg_tok = _active_config.set(None)
        try:
            await enforce_auth(spec, _FakeRequest(), user)
        finally:
            _user_var.reset(tok)
            _active_config.reset(cfg_tok)

    anyio.run(runner)


def test_scope_all_passes_with_full_set() -> None:
    user = MachineCaller(id="m", scopes=frozenset({"webhook:write", "webhook:read"}))
    _run(user, AuthSpec(scopes=("webhook:write", "webhook:read"), mode="all"))


def test_scope_all_denies_missing_one() -> None:
    user = MachineCaller(id="m", scopes=frozenset({"webhook:write"}))
    with pytest.raises(HTTPError) as exc:
        _run(user, AuthSpec(scopes=("webhook:write", "webhook:read"), mode="all"))
    assert exc.value.status == 403


def test_scope_any_passes_on_intersection() -> None:
    user = MachineCaller(id="m", scopes=frozenset({"webhook:read"}))
    _run(user, AuthSpec(scopes=("webhook:write", "webhook:read"), mode="any"))


def test_scope_any_denies_empty_intersection() -> None:
    user = MachineCaller(id="m", scopes=frozenset({"unrelated"}))
    with pytest.raises(HTTPError) as exc:
        _run(user, AuthSpec(scopes=("webhook:write", "webhook:read"), mode="any"))
    assert exc.value.status == 403


def test_scope_gate_denies_client_without_scopes_protocol() -> None:
    # A user with no scopes attribute hitting a scope gate -> 403.
    user = HumanUser(id="h", permissions=frozenset({"admin"}))
    with pytest.raises(HTTPError) as exc:
        _run(user, AuthSpec(scopes=("webhook:write",)))
    assert exc.value.status == 403


def test_empty_scopes_runs_no_scope_step() -> None:
    # An AuthSpec with no scopes never touches the scope axis: a human user with
    # no scopes attribute passes an authn-only spec.
    _run(HumanUser(id="h"), AuthSpec())


# ---------------------------------------------------------------------------
# dict / dynamic-meta parity for the 'scopes' key
# ---------------------------------------------------------------------------


def test_coerce_dict_auth_reads_scopes() -> None:
    spec = _coerce_auth({"scopes": ["webhook:write", "webhook:read"], "mode": "any"})
    assert isinstance(spec, AuthSpec)
    assert spec.scopes == ("webhook:write", "webhook:read")
    assert spec.mode == "any"


def test_dict_to_route_meta_carries_scopes() -> None:
    meta = dict_to_route_meta({"auth": {"scopes": ["webhook:write"]}})
    assert isinstance(meta.auth, AuthSpec)
    assert meta.auth.scopes == ("webhook:write",)


# ---------------------------------------------------------------------------
# End-to-end declarative gate
# ---------------------------------------------------------------------------

_TOKENS = {
    "machine_writer": MachineCaller(id="mw", scopes=frozenset({"webhook:write"})),
    "machine_reader": MachineCaller(id="mr", scopes=frozenset({"webhook:read"})),
    "human_admin": HumanUser(id="ha", permissions=frozenset({"admin"})),
}


async def _verify_token(token: str):
    return _TOKENS.get(token)


def _scope_app(scopes: tuple[str, ...], *, enforce: bool = True) -> App:
    app = App()
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="scope-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(verify_token=_verify_token, login_url="/login")))

    spec = AuthSpec(scopes=scopes) if enforce else AuthSpec()

    @app.route("/hook", methods=["POST"])
    async def hook(request):
        await enforce_route_meta_auth(RouteMeta(auth=spec), request)
        return "ok"

    return app


# ===========================================================================
# ACCEPTANCE — the two success criteria from issue #375.
# ===========================================================================


@pytest.mark.issue(375)
class TestScopeAxisAcceptance:
    async def test_scope_gate_independent_of_permissions(self) -> None:
        """Criterion 1: a machine endpoint requiring a scope succeeds for a
        token-resolved client holding that scope and 403s for one that does not,
        INDEPENDENT of human permissions."""
        app = _scope_app(("webhook:write",))

        # (a) Machine client WITH the scope but NO permissions -> 200.
        async with TestClient(app) as client:
            r = await client.post("/hook", headers={"Authorization": "Bearer machine_writer"})
            assert r.status == 200
            assert r.text == "ok"

        # (b) Machine client with a DIFFERENT scope -> 403.
        async with TestClient(app) as client:
            r = await client.post("/hook", headers={"Authorization": "Bearer machine_reader"})
            assert r.status == 403

        # (c) Human user WITH permissions but NO scope -> 403 (the scope gate is
        #     orthogonal to the permission axis).
        async with TestClient(app) as client:
            r = await client.post("/hook", headers={"Authorization": "Bearer human_admin"})
            assert r.status == 403

    async def test_scope_enforcement_off_by_default(self) -> None:
        """Criterion 2: scope enforcement is disabled by default — only active
        when an AuthSpec actually declares scopes (no separate enable flag)."""
        # No scopes declared: a permission-less, scope-less client is admitted
        # (authn-only). Existing verify_token users are never newly 403'd.
        app = _scope_app((), enforce=False)
        async with TestClient(app) as client:
            r = await client.post("/hook", headers={"Authorization": "Bearer human_admin"})
            assert r.status == 200
            # Even a machine client with NO matching scope passes when the spec
            # declares none — the scope step does not run at all.
            r2 = await client.post("/hook", headers={"Authorization": "Bearer machine_reader"})
            assert r2.status == 200

    def test_token_scope_compare_is_constant_time(self) -> None:
        """Criterion 2 (constant-time): scope equality routes through
        secrets.compare_digest, never ``==``.

        Asserted at the source level (the helper that does the comparison calls
        ``secrets.compare_digest``) AND behaviorally (the helper returns the
        right membership result). Avoids monkeypatching the shared ``secrets``
        module, which csrf/password code also uses concurrently.
        """
        import inspect

        from chirp.security.auth_core import _scope_held

        src = inspect.getsource(_scope_held)
        assert "secrets.compare_digest" in src
        assert "==" not in src.split('"""', 2)[-1]  # no == in the code body

        held = frozenset({"webhook:write", "webhook:read"})
        assert _scope_held("webhook:write", held) is True
        assert _scope_held("webhook:admin", held) is False


# ---------------------------------------------------------------------------
# Contract check — registry-backed scope validation (auth_spec category)
# ---------------------------------------------------------------------------


def _cfg(env: str):
    @dataclass(frozen=True)
    class _C:
        env: str

    return _C(env=env)


def _meta(auth):
    return RouteMeta(auth=auth)


def test_unregistered_scope_is_auth_spec_error_in_prod() -> None:
    from chirp.contracts.rules_auth_meta import check_auth_spec
    from chirp.contracts.types import Severity

    issues = check_auth_spec(
        _cfg("production"),
        {"/hook": _meta(AuthSpec(scopes=("webhook:write",)))},
        set(),
        scope_registry=frozenset({"webhook:read"}),  # write not declared
    )
    scope_issues = [i for i in issues if i.category == "auth_spec"]
    assert scope_issues
    assert all(i.severity == Severity.ERROR for i in scope_issues)
    assert any("webhook:write" in i.message for i in scope_issues)


def test_registered_scope_passes_contract() -> None:
    from chirp.contracts.rules_auth_meta import check_auth_spec

    issues = check_auth_spec(
        _cfg("production"),
        {"/hook": _meta(AuthSpec(scopes=("webhook:write",)))},
        set(),
        scope_registry=frozenset({"webhook:write"}),
    )
    assert issues == []


def test_scope_without_registry_is_not_flagged() -> None:
    """No scope registry: scopes are free strings (no typo heuristic)."""
    from chirp.contracts.rules_auth_meta import check_auth_spec

    issues = check_auth_spec(
        _cfg("production"),
        {"/hook": _meta(AuthSpec(scopes=("anything:goes",)))},
        set(),
    )
    assert issues == []


def test_register_scope_raises_after_freeze() -> None:
    app = App()
    app.register_scope("webhook:read")  # before freeze: ok
    app.freeze()
    with pytest.raises(RuntimeError):
        app.register_scope("webhook:write")

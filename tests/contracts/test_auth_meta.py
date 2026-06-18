"""Auth-wiring contract rules: auth_middleware + auth_spec.

Unit tests over stub routers / RouteMeta dicts / stub middleware, mirroring
test_cookie_secure.py / test_security_stack_rule.py. The end-to-end
orchestrator-wiring proof (the rules actually reach ``check_hypermedia_surface``)
lives at the bottom and mirrors the cookie_secure wiring tests.

Detection is by class NAME (``type(mw).__name__``), so stub class names matter.
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_auth_meta import check_auth_middleware, check_auth_spec
from chirp.pages.types import AuthSpec, RouteMeta
from chirp.security.decorators import login_required, requires

# ---------------------------------------------------------------------------
# Stubs. Detection is by class NAME.
# ---------------------------------------------------------------------------


class AuthMiddleware:
    pass


class SessionMiddleware:
    pass


class _Route:
    def __init__(self, path: str, handler=None, page_source_handler=None) -> None:
        self.path = path
        self.handler = handler or (lambda: None)
        self.page_source_handler = page_source_handler


class _Router:
    def __init__(self, routes: list[_Route]) -> None:
        self.routes = routes


def _empty_router() -> _Router:
    return _Router([])


def _meta(auth: str | None) -> RouteMeta:
    return RouteMeta(auth=auth)


# ===========================================================================
# CHECK 1 — auth_middleware
# ===========================================================================

# --- static RouteMeta.auth declares auth, no AuthMiddleware -----------------


def test_auth_required_no_authmw_errors_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(
        _empty_router(), cfg, [], {"/dashboard": _meta("required")}, set()
    )
    cats = [i.category for i in issues]
    assert "auth_middleware" in cats
    err = next(i for i in issues if i.category == "auth_middleware")
    assert err.severity.name == "ERROR"
    assert "/dashboard" in err.message


def test_auth_required_no_authmw_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_auth_middleware(
        _empty_router(), cfg, [], {"/dashboard": _meta("required")}, set()
    )
    err = next(i for i in issues if i.category == "auth_middleware")
    assert err.severity.name == "WARNING"


def test_auth_required_no_authmw_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    issues = check_auth_middleware(
        _empty_router(), cfg, [], {"/dashboard": _meta("required")}, set()
    )
    assert issues == []


def test_permission_string_declares_auth() -> None:
    """A bare permission string (e.g. 'admin') is non-open -> declares auth."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(_empty_router(), cfg, [], {"/admin": _meta("admin")}, set())
    assert any(i.category == "auth_middleware" and i.severity.name == "ERROR" for i in issues)


# --- AuthMiddleware present -> clean ----------------------------------------


def test_authmw_present_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(
        _empty_router(), cfg, [AuthMiddleware()], {"/dashboard": _meta("required")}, set()
    )
    assert issues == []


def test_authmw_present_among_others_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(
        _empty_router(),
        cfg,
        [SessionMiddleware(), AuthMiddleware()],
        {"/dashboard": _meta("required")},
        set(),
    )
    assert issues == []


# --- open auth values do NOT declare auth ----------------------------------


@pytest.mark.parametrize("auth", [None, "none", "optional"])
def test_open_auth_values_do_not_declare(auth) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(_empty_router(), cfg, [], {"/p": _meta(auth)}, set())
    assert issues == []


# --- decorator marker detection (no AuthMiddleware) -------------------------


def test_login_required_handler_detected_via_marker() -> None:
    """An @login_required @app.route handler with no AuthMiddleware is detected
    via the static _chirp_requires_auth marker the decorator stamps."""

    @login_required
    async def dashboard():  # pragma: no cover - never invoked
        return "ok"

    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _Router([_Route("/dashboard", handler=dashboard)])
    issues = check_auth_middleware(router, cfg, [], {}, set())
    assert any(i.category == "auth_middleware" and i.severity.name == "ERROR" for i in issues)
    err = next(i for i in issues if i.category == "auth_middleware")
    assert "/dashboard" in err.message


def test_requires_handler_detected_via_marker() -> None:
    @requires("admin")
    async def admin_panel():  # pragma: no cover - never invoked
        return "ok"

    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _Router([_Route("/admin", handler=admin_panel)])
    issues = check_auth_middleware(router, cfg, [], {}, set())
    assert any(i.category == "auth_middleware" and i.severity.name == "ERROR" for i in issues)


def test_marker_on_page_source_handler_detected() -> None:
    """For mounted pages the real handler is on route.page_source_handler; the
    marker is found there too."""

    @login_required
    async def page_handler():  # pragma: no cover - never invoked
        return "ok"

    async def async_wrapper():  # pragma: no cover - never invoked
        return "ok"

    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _Router([_Route("/account", handler=async_wrapper, page_source_handler=page_handler)])
    issues = check_auth_middleware(router, cfg, [], {}, set())
    assert any(i.category == "auth_middleware" for i in issues)


def test_undecorated_handler_no_marker_clean() -> None:
    async def plain():  # pragma: no cover - never invoked
        return "ok"

    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _Router([_Route("/", handler=plain)])
    issues = check_auth_middleware(router, cfg, [], {}, set())
    assert issues == []


def test_marker_handler_silent_in_development() -> None:
    @login_required
    async def dashboard():  # pragma: no cover - never invoked
        return "ok"

    cfg = AppConfig(env="development")
    router = _Router([_Route("/dashboard", handler=dashboard)])
    assert check_auth_middleware(router, cfg, [], {}, set()) == []


# --- dynamic meta() pages: INFO blind spot, NOT a false ERROR --------------


def test_meta_provider_page_is_info_blind_spot_not_error() -> None:
    """A dynamic meta() page is a static blind spot: never a false ERROR, but a
    single INFO notes auth could not be statically verified."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(_empty_router(), cfg, [], {"/dyn": None}, {"/dyn"})
    cats = {(i.category, i.severity.name) for i in issues}
    assert ("auth_middleware", "INFO") in cats
    # No ERROR — the page is excluded from static auth detection.
    assert not any(i.severity.name == "ERROR" for i in issues)
    info = next(i for i in issues if i.severity.name == "INFO")
    assert "/dyn" in info.message


def test_meta_provider_blind_spot_silent_when_authmw_present() -> None:
    """With AuthMiddleware present there is nothing to warn about, so no INFO."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(
        _empty_router(), cfg, [AuthMiddleware()], {"/dyn": None}, {"/dyn"}
    )
    assert issues == []


def test_meta_provider_path_excluded_from_static_error() -> None:
    """Even with a non-open static meta accidentally present for a provider path,
    the provider path is skipped from the ERROR branch (blind spot)."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_middleware(_empty_router(), cfg, [], {"/dyn": _meta("required")}, {"/dyn"})
    # Only the INFO note, no ERROR for the provider path.
    assert not any(i.severity.name == "ERROR" for i in issues)
    assert any(i.severity.name == "INFO" for i in issues)


# ===========================================================================
# CHECK 2 — auth_spec (silent-403 permission typo)
# ===========================================================================


@pytest.mark.parametrize(
    "auth", ["requied", "Required", "REQUIRED", " required ", "None", "Optional"]
)
def test_auth_spec_fires_on_typos_in_production(auth) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_spec(cfg, {"/p": _meta(auth)}, set())
    assert [i.category for i in issues] == ["auth_spec"]
    assert issues[0].severity.name == "ERROR"
    assert repr(auth) in issues[0].message
    assert "/p" in issues[0].message


def test_auth_spec_typo_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_auth_spec(cfg, {"/p": _meta("Required")}, set())
    assert [i.category for i in issues] == ["auth_spec"]
    assert issues[0].severity.name == "WARNING"


def test_auth_spec_typo_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    assert check_auth_spec(cfg, {"/p": _meta("Required")}, set()) == []


def test_auth_spec_whitespace_only_fires() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_spec(cfg, {"/p": _meta("   ")}, set())
    assert [i.category for i in issues] == ["auth_spec"]


@pytest.mark.parametrize("auth", ["required", "none", "optional"])
def test_auth_spec_clean_on_exact_reserved(auth) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/p": _meta(auth)}, set()) == []


@pytest.mark.parametrize("auth", ["admin", "editor", "moderator", "billing.read"])
def test_auth_spec_clean_on_plausible_permissions(auth) -> None:
    """Plausible permission names are NOT flagged — no registry to validate them,
    and false positives erode trust."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/p": _meta(auth)}, set()) == []


@pytest.mark.parametrize("auth", ["node", "note", "nine", "opt", "optic"])
def test_auth_spec_clean_on_open_token_neighbours(auth) -> None:
    """The near-miss typo branch is scoped to 'required' ONLY. Words near the
    short open tokens (none/optional) are real words / plausible permissions and
    must NOT be flagged — only case/whitespace variants of them are."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/p": _meta(auth)}, set()) == []


def test_auth_spec_clean_on_open_values() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/a": _meta(None), "/b": _meta("none")}, set()) == []


def test_auth_spec_skips_meta_provider_paths() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/dyn": _meta("Required")}, {"/dyn"}) == []


# ===========================================================================
# CHECK 2b — auth_spec REGISTRY-BACKED (permission + policy registries)
# ===========================================================================


def test_auth_spec_unregistered_permission_errors_with_registry() -> None:
    """With a permission registry declared, a permission not in it is an ERROR —
    even a plausible name like 'admin' (the registry is the source of truth)."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_spec(
        cfg,
        {"/p": _meta("admin")},
        set(),
        permission_registry=frozenset({"editor"}),
    )
    assert [i.category for i in issues] == ["auth_spec"]
    assert issues[0].severity.name == "ERROR"
    assert "'admin'" in issues[0].message
    assert "/p" in issues[0].message


def test_auth_spec_registered_permission_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_spec(
        cfg,
        {"/p": _meta("admin")},
        set(),
        permission_registry=frozenset({"admin", "editor"}),
    )
    assert issues == []


def test_auth_spec_registry_validates_authspec_permissions() -> None:
    """A structured AuthSpec's permissions are validated against the registry."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    meta = RouteMeta(auth=AuthSpec(permissions=("admin", "ghost"), mode="all"))
    issues = check_auth_spec(
        cfg,
        {"/p": meta},
        set(),
        permission_registry=frozenset({"admin", "editor"}),
    )
    # 'ghost' is unregistered -> exactly one ERROR; 'admin' is fine.
    assert [i.category for i in issues] == ["auth_spec"]
    assert "'ghost'" in issues[0].message


def test_auth_spec_heuristic_only_without_registry() -> None:
    """With no registry, a plausible name is NOT flagged (heuristic-only mode);
    a reserved-token confusion still is."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_auth_spec(cfg, {"/p": _meta("admin")}, set()) == []
    typo = check_auth_spec(cfg, {"/p": _meta("Required")}, set())
    assert [i.category for i in typo] == ["auth_spec"]


def test_auth_spec_unregistered_policy_errors() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    meta = RouteMeta(auth=AuthSpec(policy="is_owner"))
    issues = check_auth_spec(
        cfg,
        {"/p": meta},
        set(),
        policy_registry=frozenset({"is_admin"}),
    )
    assert [i.category for i in issues] == ["auth_spec"]
    assert "'is_owner'" in issues[0].message
    assert issues[0].severity.name == "ERROR"


def test_auth_spec_registered_policy_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    meta = RouteMeta(auth=AuthSpec(policy="is_owner"))
    issues = check_auth_spec(
        cfg,
        {"/p": meta},
        set(),
        policy_registry=frozenset({"is_owner"}),
    )
    assert issues == []


def test_auth_spec_policy_errors_with_empty_registry_in_production() -> None:
    """ASYMMETRY: a referenced AuthSpec.policy must ALWAYS resolve — an
    AuthSpec(policy='x') with NO policy registered (empty registry) is an ERROR
    in production, because it 500s at request time. Unlike permissions, this is
    NOT opt-in on a non-empty registry."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    meta = RouteMeta(auth=AuthSpec(policy="is_owner"))
    # No policy_registry kwarg -> empty registry.
    issues = check_auth_spec(cfg, {"/p": meta}, set())
    assert [i.category for i in issues] == ["auth_spec"]
    assert issues[0].severity.name == "ERROR"
    assert "'is_owner'" in issues[0].message
    assert "/p" in issues[0].message


def test_auth_spec_policy_empty_registry_silent_in_development() -> None:
    """Still env-aware: silent in development even with an unresolved policy."""
    cfg = AppConfig(env="development")
    meta = RouteMeta(auth=AuthSpec(policy="is_owner"))
    assert check_auth_spec(cfg, {"/p": meta}, set()) == []


def test_auth_spec_policy_registered_clean_with_register_policy() -> None:
    """AuthSpec(policy='is_owner') + register_policy('is_owner') -> clean, even
    though the permission asymmetry leaves a non-policy registry empty."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    meta = RouteMeta(auth=AuthSpec(policy="is_owner"))
    issues = check_auth_spec(cfg, {"/p": meta}, set(), policy_registry=frozenset({"is_owner"}))
    assert issues == []


def test_auth_spec_policy_only_registry_does_not_false_error_permissions() -> None:
    """A policy-only registry must not ERROR on plausible permission names —
    permission validation needs a PERMISSION registry, not a policy one."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_auth_spec(
        cfg,
        {"/p": _meta("admin")},
        set(),
        policy_registry=frozenset({"is_owner"}),
    )
    assert issues == []


# ===========================================================================
# --deploy escalation: dev-silent, escalates under deploy posture.
# ===========================================================================


@pytest.mark.issue(220)
def test_deploy_posture_escalates_auth_middleware(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )

    @app.route("/dashboard")
    @login_required
    async def dashboard():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_middleware"]
    assert not any(i.severity.name in ("ERROR", "WARNING") for i in dev), (
        "auth_middleware should be silent in development posture"
    )

    deploy = [
        i
        for i in check_hypermedia_surface(app, deploy=True).issues
        if i.category == "auth_middleware"
    ]
    assert any(i.severity.name == "ERROR" for i in deploy), (
        "auth_middleware did not escalate under deploy posture"
    )
    assert app.config.env == "development"


@pytest.mark.issue(220)
def test_deploy_posture_escalates_auth_spec(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )

    @app.route("/")
    async def home():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()
    # Inject a typo'd static RouteMeta directly (mounted pages own _meta.py; this
    # exercises the rule's read of snapshot.route_metas without a pages tree).
    app._mutable_state.route_metas["/p"] = RouteMeta(auth="Required")

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_spec"]
    assert not dev, "auth_spec should be silent in development posture"

    deploy = [
        i for i in check_hypermedia_surface(app, deploy=True).issues if i.category == "auth_spec"
    ]
    assert any(i.severity.name == "ERROR" for i in deploy), (
        "auth_spec did not escalate under deploy posture"
    )
    assert app.config.env == "development"


# ===========================================================================
# Orchestrator wiring: the rules actually reach check_hypermedia_surface.
# A regression dropping the result.issues.extend in checker.py would leave the
# unit tests green but disable the rule.
# ===========================================================================


@pytest.mark.issue(220)
def test_auth_middleware_fires_through_orchestrator(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/dashboard")
    @login_required
    async def dashboard():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_middleware"]
    assert any(i.severity.name == "ERROR" for i in issues), (
        "auth_middleware did not fire through check_hypermedia_surface"
    )


@pytest.mark.issue(220)
def test_auth_middleware_clean_through_orchestrator_with_authmw(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.auth import AuthConfig
    from chirp.middleware.auth import AuthMiddleware as RealAuthMiddleware
    from chirp.middleware.sessions import SessionConfig
    from chirp.middleware.sessions import SessionMiddleware as RealSessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.add_middleware(RealSessionMiddleware(SessionConfig(secret_key="x" * 32)))
    app.add_middleware(
        RealAuthMiddleware(AuthConfig(load_user=lambda _id: None, verify_token=lambda _t: None))
    )

    @app.route("/dashboard")
    @login_required
    async def dashboard():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_middleware"]
    assert not issues, "auth_middleware should be clean when AuthMiddleware is registered"


@pytest.mark.issue(220)
def test_auth_spec_fires_through_orchestrator(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/")
    async def home():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()
    app._mutable_state.route_metas["/p"] = RouteMeta(auth="Required")

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_spec"]
    assert any(i.severity.name == "ERROR" for i in issues), (
        "auth_spec did not fire through check_hypermedia_surface"
    )


@pytest.mark.issue(220)
def test_auth_spec_registry_backed_fires_through_orchestrator(tmp_path) -> None:
    """A declared permission registry threads through the snapshot to the check:
    an unregistered AuthSpec permission ERRORs through check_hypermedia_surface."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.register_permission("editor")

    @app.route("/")
    async def home():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()
    # 'admin' is plausible (heuristic would NOT flag it) but is NOT registered.
    app._mutable_state.route_metas["/p"] = RouteMeta(
        auth=AuthSpec(permissions=("admin",), mode="all")
    )

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_spec"]
    assert any(i.severity.name == "ERROR" and "'admin'" in i.message for i in issues), (
        "registry-backed auth_spec did not fire through check_hypermedia_surface"
    )


@pytest.mark.issue(220)
def test_auth_spec_registry_backed_clean_when_registered(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.register_permission("admin")

    @app.route("/")
    async def home():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()
    app._mutable_state.route_metas["/p"] = RouteMeta(
        auth=AuthSpec(permissions=("admin",), mode="all")
    )

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "auth_spec"]
    assert not issues, "registered permission should be clean"

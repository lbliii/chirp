"""Cookie-hardening contract rules (Wave 2): cookie_secure + hsts.

Unit tests over a stub router + AppConfig + stub middleware, mirroring
test_security_stack_rule.py / test_deploy_preflight.py. The end-to-end
orchestrator-wiring proof (the rule actually reaches ``check_hypermedia_surface``)
lives at the bottom and mirrors test_rule_wiring.py.
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_cookie_secure import check_cookie_secure, check_hsts

# ---------------------------------------------------------------------------
# Stubs. Detection is by class NAME, so the names matter.
# ---------------------------------------------------------------------------


class _StoreConfig:
    """Mirror the SessionConfig fields the rule reads off a store's _config."""

    def __init__(self, secure: object, samesite: str = "lax") -> None:
        self.secure = secure
        self.samesite = samesite


class _Store:
    def __init__(self, config: _StoreConfig) -> None:
        self._config = config


class SessionMiddleware:
    """Stub mirroring chirp's SessionMiddleware secure accessor + store config.

    The real middleware exposes ``secure`` (reading the store's config) and keeps
    the store at ``_store`` (with the config at ``_store._config``). The rule
    reads ``mw.secure`` for the secure flag and ``mw._store._config.samesite`` for
    samesite, so the stub provides both.
    """

    def __init__(self, secure: object, samesite: str = "lax") -> None:
        self._store = _Store(_StoreConfig(secure, samesite))

    @property
    def configured_secure(self) -> object:
        # The rule reads the originally-configured value; for the stub (which
        # never goes through freeze resolution) it equals ``secure``.
        return self._store._config.secure

    @property
    def secure(self) -> object:
        return self._store._config.secure


class SecurityHeadersMiddleware:
    class _Cfg:
        def __init__(self, hsts: str | None) -> None:
            self.strict_transport_security = hsts

    def __init__(self, hsts: str | None = None) -> None:
        self.config = SecurityHeadersMiddleware._Cfg(hsts)


class _Route:
    def __init__(self, path: str, methods: set[str]) -> None:
        self.path = path
        self.methods = methods


class _Router:
    def __init__(self, routes: list[_Route]) -> None:
        self.routes = routes


def _mutating_router() -> _Router:
    return _Router([_Route("/save", {"POST"})])


def _readonly_router() -> _Router:
    return _Router([_Route("/", {"GET"})])


# ---------------------------------------------------------------------------
# cookie_secure — env-aware hardening gap (secure resolves False)
# ---------------------------------------------------------------------------


def test_insecure_cookie_errors_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False)])
    assert [i.category for i in issues] == ["cookie_secure"]
    assert issues[0].severity.name == "ERROR"


def test_insecure_cookie_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False)])
    assert [i.category for i in issues] == ["cookie_secure"]
    assert issues[0].severity.name == "WARNING"


def test_insecure_cookie_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    assert check_cookie_secure(cfg, [SessionMiddleware(secure=False)]) == []


# ---------------------------------------------------------------------------
# cookie_secure — "auto" happy path: resolves True in prod/staging -> silent
# ---------------------------------------------------------------------------


def test_auto_secure_is_clean_in_production() -> None:
    """The blessed default secure='auto' resolves True under production posture,
    so a default-config app ships a Secure cookie with no issue."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_cookie_secure(cfg, [SessionMiddleware(secure="auto")]) == []


def test_auto_secure_is_clean_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    assert check_cookie_secure(cfg, [SessionMiddleware(secure="auto")]) == []


def test_auto_secure_is_clean_in_development() -> None:
    """'auto' resolves False in dev (cookie not Secure) but dev is silent."""
    cfg = AppConfig(env="development")
    assert check_cookie_secure(cfg, [SessionMiddleware(secure="auto")]) == []


def test_explicit_true_secure_is_clean_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_cookie_secure(cfg, [SessionMiddleware(secure=True)]) == []


# ---------------------------------------------------------------------------
# cookie_secure — store-agnostic (RedisSessionStore session-id cookie)
# ---------------------------------------------------------------------------


def test_insecure_cookie_flagged_regardless_of_store() -> None:
    """A Secure-less session-id cookie (Redis store) is equally exploitable, so
    the rule fires on the effective secure flag, not the store type. The stub's
    secure flag is what matters; this asserts the rule does not special-case a
    store."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False, samesite="lax")])
    assert issues
    assert issues[0].severity.name == "ERROR"


# ---------------------------------------------------------------------------
# cookie_secure — env-INDEPENDENT ERROR for samesite='none' + insecure
# ---------------------------------------------------------------------------


def test_samesite_none_insecure_errors_in_development() -> None:
    """SameSite=None without Secure is silently dropped by browsers in EVERY env,
    so it is an ERROR even in development (where the hardening gap is silent)."""
    cfg = AppConfig(env="development")
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False, samesite="none")])
    assert [i.category for i in issues] == ["cookie_secure"]
    assert issues[0].severity.name == "ERROR"
    assert "SameSite=None" in issues[0].message


def test_samesite_none_insecure_errors_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False, samesite="none")])
    assert issues[0].severity.name == "ERROR"
    assert "SameSite=None" in issues[0].message


def test_samesite_none_with_secure_is_clean() -> None:
    """SameSite=None WITH Secure is valid — no issue."""
    cfg = AppConfig(env="development")
    assert check_cookie_secure(cfg, [SessionMiddleware(secure=True, samesite="none")]) == []


def test_samesite_none_case_insensitive() -> None:
    cfg = AppConfig(env="development")
    issues = check_cookie_secure(cfg, [SessionMiddleware(secure=False, samesite="None")])
    assert issues
    assert issues[0].severity.name == "ERROR"


# ---------------------------------------------------------------------------
# cookie_secure — no-op without SessionMiddleware (security_stack owns presence)
# ---------------------------------------------------------------------------


def test_no_session_middleware_is_noop_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_cookie_secure(cfg, []) == []


def test_no_session_middleware_with_other_middleware_is_noop() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_cookie_secure(cfg, [SecurityHeadersMiddleware()]) == []


# ---------------------------------------------------------------------------
# hsts — production + unset + mutating surface -> WARNING
# ---------------------------------------------------------------------------


def test_hsts_warns_in_production_with_mutating_surface() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_hsts(_mutating_router(), cfg, [])
    assert [i.category for i in issues] == ["hsts"]
    assert issues[0].severity.name == "WARNING"


def test_hsts_silent_when_no_mutating_surface() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_hsts(_readonly_router(), cfg, []) == []


def test_hsts_silent_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    assert check_hsts(_mutating_router(), cfg, []) == []


def test_hsts_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    assert check_hsts(_mutating_router(), cfg, []) == []


def test_hsts_silent_when_set_on_config() -> None:
    cfg = AppConfig(
        env="production",
        secret_key="x" * 32,
        strict_transport_security="max-age=63072000; includeSubDomains",
    )
    assert check_hsts(_mutating_router(), cfg, []) == []


def test_hsts_silent_when_set_on_security_headers_middleware() -> None:
    """HSTS configured only on a hand-added SecurityHeadersMiddleware must not
    produce a false WARNING."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    mws = [SecurityHeadersMiddleware(hsts="max-age=63072000")]
    assert check_hsts(_mutating_router(), cfg, mws) == []


def test_hsts_warns_when_security_headers_present_but_hsts_unset() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    mws = [SecurityHeadersMiddleware(hsts=None)]
    issues = check_hsts(_mutating_router(), cfg, mws)
    assert [i.category for i in issues] == ["hsts"]


def test_hsts_silent_when_ssl_certfile_set_in_production() -> None:
    """No false WARNING when the compiler will auto-wire HSTS: in production with
    ssl_certfile set (TLS terminated in-process), the runtime DOES emit HSTS even
    though strict_transport_security is unset here, so nudging would be wrong."""
    cfg = AppConfig(env="production", secret_key="x" * 32, ssl_certfile="cert.pem")
    assert check_hsts(_mutating_router(), cfg, []) == []


def test_hsts_never_errors() -> None:
    """HSTS is a WARNING-only nudge — it is never promoted to ERROR, even in
    production. (Irreversible multi-year browser pin: a declared-env guess must
    not auto-emit it.)"""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_hsts(_mutating_router(), cfg, [])
    assert all(i.severity.name == "WARNING" for i in issues)


# ---------------------------------------------------------------------------
# --deploy escalation: parallels the secret_key/allowed_hosts deploy tests.
# A development app passes cookie_secure/hsts in dev posture but escalates under
# deploy=True (production-posture view), without mutating the real config.
# ---------------------------------------------------------------------------


@pytest.mark.issue(220)
def test_deploy_posture_escalates_cookie_secure(tmp_path) -> None:
    """A dev app with an insecure session cookie is silent in dev but ERRORs
    under deploy posture, while the real config keeps env='development'."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )
    # Explicit secure=False: resolves False in EVERY env, so deploy posture
    # exposes the production hardening gap.
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32, secure=False)))

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "cookie_secure"]
    assert not dev, "cookie_secure should be silent in development posture"

    deploy = [
        i
        for i in check_hypermedia_surface(app, deploy=True).issues
        if i.category == "cookie_secure"
    ]
    assert deploy, "cookie_secure did not escalate under deploy posture"
    assert any(i.severity.name == "ERROR" for i in deploy)

    # The deploy posture never mutates the user's real config.
    assert app.config.env == "development"


@pytest.mark.issue(220)
def test_deploy_posture_clean_for_auto_default_frozen_in_dev(tmp_path) -> None:
    """Negative control / regression: the blessed secure='auto' default, frozen
    in DEVELOPMENT (freeze resolves the cookie to not-Secure for local HTTP),
    must STILL pass under deploy posture. --deploy re-resolves the *configured*
    'auto' against production -> Secure -> clean. Reading the freeze-resolved
    bool instead would falsely ERROR every `chirp new` scaffold under --deploy.
    """
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )
    # secure='auto' (the default): resolves to NOT-Secure at freeze for dev.
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()  # resolves 'auto' -> False for development; configured stays 'auto'

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "cookie_secure"]
    assert not dev, "auto default must be clean in development posture"

    deploy = [
        i
        for i in check_hypermedia_surface(app, deploy=True).issues
        if i.category == "cookie_secure"
    ]
    assert not deploy, (
        "auto default (deploy-ready) must NOT ERROR under deploy posture — the "
        "check must re-resolve the configured 'auto', not the dev-frozen bool"
    )
    assert app.config.env == "development"


@pytest.mark.issue(220)
def test_deploy_posture_escalates_hsts(tmp_path) -> None:
    """A dev app with a mutating surface and no HSTS is silent in dev but WARNs
    under deploy posture (which --deploy treats as an error via
    warnings-as-errors)."""
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

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "hsts"]
    assert not dev, "hsts should be silent in development posture"

    deploy = [i for i in check_hypermedia_surface(app, deploy=True).issues if i.category == "hsts"]
    assert deploy, "hsts did not surface under deploy posture"
    assert all(i.severity.name == "WARNING" for i in deploy)
    assert app.config.env == "development"


# ---------------------------------------------------------------------------
# Orchestrator wiring: the rules actually reach check_hypermedia_surface.
# Mirrors test_rule_wiring.py — a regression dropping the result.issues.extend
# line in checker.py would leave the unit tests green but disable the rule.
# ---------------------------------------------------------------------------


@pytest.mark.issue(220)
def test_cookie_secure_fires_through_orchestrator(tmp_path) -> None:
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32, secure=False)))

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "cookie_secure"]
    assert issues, "cookie_secure did not fire through check_hypermedia_surface"
    assert any(i.severity.name == "ERROR" for i in issues)


@pytest.mark.issue(220)
def test_cookie_secure_silent_through_orchestrator_for_auto(tmp_path) -> None:
    """Negative control: the blessed secure='auto' default resolves Secure in
    production, so the orchestrator emits no cookie_secure issue."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))  # secure='auto'

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "cookie_secure"]
    assert not issues


@pytest.mark.issue(220)
def test_hsts_fires_through_orchestrator(tmp_path) -> None:
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

    @app.route("/save", methods=["POST"])
    async def save():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "hsts"]
    assert issues, "hsts did not fire through check_hypermedia_surface"
    assert all(i.severity.name == "WARNING" for i in issues)

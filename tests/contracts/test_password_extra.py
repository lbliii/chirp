"""password_extra contract rule (#220): argon2-in-production deploy advisory.

Unit tests over a stub router + AppConfig, mirroring test_cookie_secure.py /
test_security_stack_rule.py. The rule imports ``_has_argon2`` lazily from
``chirp.security.passwords`` inside the function body, so the monkeypatch target
is the source module attribute ``chirp.security.passwords._has_argon2``. The
end-to-end orchestrator-wiring proof lives at the bottom and mirrors
test_cookie_secure.py.
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_password_extra import check_password_extra

# ---------------------------------------------------------------------------
# Stubs.
# ---------------------------------------------------------------------------


class _Route:
    def __init__(self, path: str, methods: set[str]) -> None:
        self.path = path
        self.methods = methods


class _PageRoute:
    """A GET-only filesystem page that mutates via _actions.py form actions."""

    def __init__(self, path: str, actions: tuple[str, ...]) -> None:
        self.path = path
        self.methods = {"GET"}
        self.actions = actions


class _Router:
    def __init__(self, routes: list[object]) -> None:
        self.routes = routes


def _mutating_router() -> _Router:
    return _Router([_Route("/login", {"POST"})])


def _readonly_router() -> _Router:
    return _Router([_Route("/", {"GET"})])


@pytest.fixture
def no_argon2(monkeypatch) -> None:
    monkeypatch.setattr("chirp.security.passwords._has_argon2", lambda: False)


@pytest.fixture
def with_argon2(monkeypatch) -> None:
    monkeypatch.setattr("chirp.security.passwords._has_argon2", lambda: True)


# ---------------------------------------------------------------------------
# password_extra — env-aware advisory when argon2 is unavailable
# ---------------------------------------------------------------------------


def test_warns_in_production_when_argon2_unavailable(no_argon2) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_password_extra(_mutating_router(), cfg)
    assert [i.category for i in issues] == ["password_extra"]
    assert issues[0].severity.name == "WARNING"
    assert "chirp[auth]" in issues[0].message


def test_warns_in_staging_when_argon2_unavailable(no_argon2) -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_password_extra(_mutating_router(), cfg)
    assert [i.category for i in issues] == ["password_extra"]
    assert issues[0].severity.name == "WARNING"


def test_silent_in_development_when_argon2_unavailable(no_argon2) -> None:
    """Silent in dev so dev apps + shipped examples + scrypt-only CI stay clean."""
    cfg = AppConfig(env="development")
    assert check_password_extra(_mutating_router(), cfg) == []


def test_never_errors(no_argon2) -> None:
    """password_extra is an advisory — never promoted to ERROR (scrypt is fine)."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_password_extra(_mutating_router(), cfg)
    assert all(i.severity.name == "WARNING" for i in issues)


# ---------------------------------------------------------------------------
# password_extra — silent when argon2 IS available
# ---------------------------------------------------------------------------


def test_silent_in_production_when_argon2_available(with_argon2) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_password_extra(_mutating_router(), cfg) == []


def test_silent_in_staging_when_argon2_available(with_argon2) -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    assert check_password_extra(_mutating_router(), cfg) == []


# ---------------------------------------------------------------------------
# password_extra — no mutating surface => no-op even without argon2
# ---------------------------------------------------------------------------


def test_silent_without_mutating_surface(no_argon2) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_password_extra(_readonly_router(), cfg) == []


def test_fires_for_action_only_page_surface(no_argon2) -> None:
    """A GET-only filesystem page backed by _actions.py form actions counts as a
    mutating/login surface (the same is_mutating_route definition security_stack
    owns), so the advisory fires even with no POST router route."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _readonly_router()
    discovered = [_PageRoute("/settings", actions=("save",))]
    issues = check_password_extra(router, cfg, discovered)
    assert [i.category for i in issues] == ["password_extra"]


# ---------------------------------------------------------------------------
# --deploy escalation + orchestrator wiring (mirrors test_cookie_secure.py).
# These exercise the REAL _has_argon2 via the orchestrator. In the scrypt-only
# base CI env argon2 is absent so the warning fires under deploy posture; when
# argon2-cffi IS installed (e.g. `uv run --with argon2-cffi`) the rule is silent,
# so these tests gate on the real availability to stay correct in both envs.
# ---------------------------------------------------------------------------


@pytest.mark.issue(220)
def test_deploy_posture_escalates_password_extra(tmp_path) -> None:
    """A dev app with a login surface is silent in dev. Under deploy posture it
    WARNs IFF argon2 is genuinely unavailable; otherwise it stays silent. Either
    way the real config keeps env='development'."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface
    from chirp.security.passwords import _has_argon2

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )

    @app.route("/login", methods=["POST"])
    async def do_login():  # pragma: no cover - never invoked
        return "ok"

    app.freeze()

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "password_extra"]
    assert not dev, "password_extra should be silent in development posture"

    deploy = [
        i
        for i in check_hypermedia_surface(app, deploy=True).issues
        if i.category == "password_extra"
    ]
    if _has_argon2():
        assert not deploy, "password_extra must be silent when argon2 is available"
    else:
        assert deploy, "password_extra did not escalate under deploy posture"
        assert all(i.severity.name == "WARNING" for i in deploy)

    assert app.config.env == "development"


@pytest.mark.issue(220)
def test_password_extra_fires_through_orchestrator(monkeypatch, tmp_path) -> None:
    """The rule actually reaches check_hypermedia_surface. Force argon2 absent so
    the assertion is deterministic regardless of the agent's env."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    monkeypatch.setattr("chirp.security.passwords._has_argon2", lambda: False)

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/login", methods=["POST"])
    async def do_login():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "password_extra"]
    assert issues, "password_extra did not fire through check_hypermedia_surface"
    assert all(i.severity.name == "WARNING" for i in issues)


@pytest.mark.issue(220)
def test_password_extra_silent_through_orchestrator_with_argon2(monkeypatch, tmp_path) -> None:
    """Negative control: argon2 available -> orchestrator emits no password_extra."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    monkeypatch.setattr("chirp.security.passwords._has_argon2", lambda: True)

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/login", methods=["POST"])
    async def do_login():  # pragma: no cover - never invoked
        return "ok"

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "password_extra"]
    assert not issues

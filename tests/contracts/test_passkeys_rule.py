"""passkeys contract rule: webauthn-dep ERROR; cookie sessions stay first-class (#871).

Unit tests over AppConfig + stub middleware, mirroring test_password_extra.py /
test_cookie_secure.py. The rule imports ``_has_webauthn`` lazily from
``chirp.security.passkeys`` inside the function body, so the monkeypatch target
is the source attribute ``chirp.security.passkeys._has_webauthn``. Cookie-store
session posture no longer emits a Redis-preferring WARNING (#871).
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_passkeys import check_passkeys

# -- Stubs (call-site parity; middleware list is unused by the rule since #871). --


class CookieSessionStore:
    pass


class RedisSessionStore:
    pass


class SessionMiddleware:
    def __init__(self, store: object) -> None:
        self._store = store


def _cookie_stack() -> list[object]:
    return [SessionMiddleware(CookieSessionStore())]


def _redis_stack() -> list[object]:
    return [SessionMiddleware(RedisSessionStore())]


@pytest.fixture
def no_webauthn(monkeypatch) -> None:
    monkeypatch.setattr("chirp.security.passkeys._has_webauthn", lambda: False)


@pytest.fixture
def with_webauthn(monkeypatch) -> None:
    monkeypatch.setattr("chirp.security.passkeys._has_webauthn", lambda: True)


# ---------------------------------------------------------------------------
# Gate: no-op unless passkeys=True.
# ---------------------------------------------------------------------------


def test_noop_when_passkeys_disabled(no_webauthn) -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)  # passkeys defaults False
    assert check_passkeys(cfg, _cookie_stack()) == []


# ---------------------------------------------------------------------------
# webauthn missing → ERROR, env-INDEPENDENT (broken in every environment).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_webauthn_missing_errors_in_every_env(no_webauthn, env) -> None:
    cfg = AppConfig(passkeys=True, env=env, secret_key="x" * 32)
    issues = check_passkeys(cfg, _redis_stack())
    errors = [i for i in issues if i.severity.name == "ERROR"]
    assert [i.category for i in errors] == ["passkeys"]
    assert "chirp[passkeys]" in errors[0].message


def test_webauthn_present_no_error(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    issues = check_passkeys(cfg, _redis_stack())
    assert not [i for i in issues if i.severity.name == "ERROR"]


# ---------------------------------------------------------------------------
# Cookie sessions remain first-class — no Redis-preferring WARNING (#871).
# ---------------------------------------------------------------------------


@pytest.mark.issue(871)
@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_cookie_store_no_redis_recommendation(with_webauthn, env) -> None:
    cfg = AppConfig(passkeys=True, env=env, secret_key="x" * 32)
    assert check_passkeys(cfg, _cookie_stack()) == []


@pytest.mark.issue(871)
def test_redis_store_silent_when_webauthn_present(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    assert check_passkeys(cfg, _redis_stack()) == []


@pytest.mark.issue(871)
def test_webauthn_missing_in_prod_reports_error_only(no_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    issues = check_passkeys(cfg, _cookie_stack())
    assert [i.severity.name for i in issues] == ["ERROR"]
    assert all(i.category == "passkeys" for i in issues)


# ---------------------------------------------------------------------------
# Orchestrator wiring (mirrors test_password_extra.py).
# ---------------------------------------------------------------------------


def test_passkeys_rule_fires_through_orchestrator(monkeypatch, tmp_path) -> None:
    """The rule actually reaches check_hypermedia_surface. Force webauthn absent
    so the ERROR is deterministic regardless of the agent's env."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    monkeypatch.setattr("chirp.security.passkeys._has_webauthn", lambda: False)

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
            passkeys=True,
        )
    )
    app.freeze()

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "passkeys"]
    assert [i.severity.name for i in issues] == ["ERROR"], (
        "webauthn-missing must be an env-independent ERROR through the orchestrator"
    )
    assert app.config.env == "development"


@pytest.mark.issue(871)
def test_cookie_passkeys_clean_under_deploy(monkeypatch, tmp_path) -> None:
    """Cookie-backed passkeys stay clean under --deploy (no Redis nudge)."""
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    monkeypatch.setattr("chirp.security.passkeys._has_webauthn", lambda: True)

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
            passkeys=True,
        )
    )

    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))
    app.freeze()

    deploy = [
        i for i in check_hypermedia_surface(app, deploy=True).issues if i.category == "passkeys"
    ]
    assert deploy == []
    assert app.config.env == "development"

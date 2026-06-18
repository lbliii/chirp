"""passkeys contract rule (Wave 5): webauthn-dep ERROR + cookie-store WARNING.

Unit tests over AppConfig + stub middleware, mirroring test_password_extra.py /
test_cookie_secure.py. The rule imports ``_has_webauthn`` lazily from
``chirp.security.passkeys`` inside the function body, so the monkeypatch target
is the source attribute ``chirp.security.passkeys._has_webauthn``. The
store/middleware are detected by class NAME, so the stubs are named to match.
The orchestrator-wiring proof is at the bottom (mirrors test_password_extra.py).
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_passkeys import check_passkeys

# -- Stubs (class names are load-bearing — the rule uses type(x).__name__). --


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
    issues = check_passkeys(cfg, _redis_stack())  # redis → no bloat warning to confuse
    errors = [i for i in issues if i.severity.name == "ERROR"]
    assert [i.category for i in errors] == ["passkeys"]
    assert "chirp[passkeys]" in errors[0].message


def test_webauthn_present_no_error(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    issues = check_passkeys(cfg, _redis_stack())
    assert not [i for i in issues if i.severity.name == "ERROR"]


# ---------------------------------------------------------------------------
# Cookie-store challenge bloat → WARNING, env-aware (prod/staging, silent dev).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["production", "staging"])
def test_cookie_store_warns_in_prod_and_staging(with_webauthn, env) -> None:
    cfg = AppConfig(passkeys=True, env=env, secret_key="x" * 32)
    issues = check_passkeys(cfg, _cookie_stack())
    warnings = [i for i in issues if i.severity.name == "WARNING"]
    assert [i.category for i in warnings] == ["passkeys"]
    assert "CookieSessionStore" in warnings[0].message


def test_cookie_store_silent_in_development(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="development", secret_key="x" * 32)
    assert check_passkeys(cfg, _cookie_stack()) == []


def test_redis_store_no_bloat_warning(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    assert check_passkeys(cfg, _redis_stack()) == []


def test_only_one_bloat_warning(with_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    stack = [SessionMiddleware(CookieSessionStore()), SessionMiddleware(CookieSessionStore())]
    warnings = [i for i in check_passkeys(cfg, stack) if i.severity.name == "WARNING"]
    assert len(warnings) == 1


def test_webauthn_missing_and_cookie_store_in_prod_reports_both(no_webauthn) -> None:
    cfg = AppConfig(passkeys=True, env="production", secret_key="x" * 32)
    issues = check_passkeys(cfg, _cookie_stack())
    severities = sorted(i.severity.name for i in issues)
    assert severities == ["ERROR", "WARNING"]
    assert all(i.category == "passkeys" for i in issues)


# ---------------------------------------------------------------------------
# Orchestrator wiring + --deploy escalation (mirrors test_password_extra.py).
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


def test_cookie_bloat_escalates_under_deploy(monkeypatch, tmp_path) -> None:
    """Cookie-store bloat is silent in dev posture and WARNs under --deploy."""
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

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "passkeys"]
    assert not dev, "cookie-store bloat should be silent in development posture"

    deploy = [
        i for i in check_hypermedia_surface(app, deploy=True).issues if i.category == "passkeys"
    ]
    assert [i.severity.name for i in deploy] == ["WARNING"]
    assert app.config.env == "development"

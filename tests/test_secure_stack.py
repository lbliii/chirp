"""Tests for ``secure_stack`` — the one-call secure-by-default stack helper.

``secure_stack(config)`` returns the secure-by-default middleware list in the
contract-passing order (Session -> CSRF -> SecurityHeaders) without
force-injecting anything. These tests assert:

- the exact classes, in the exact order;
- the generated stack passes ``check_security_stack`` and
  ``check_csrf_session_order`` (the order contract);
- the cookie ``Secure`` flag is **env-derived, not debug-derived** — a
  ``debug=True`` + ``env="production"`` config resolves Secure, while a
  ``debug=False`` + ``env="development"`` config does not;
- ``secret_key`` flows from the app config.
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_safety import check_csrf_session_order
from chirp.contracts.rules_security_stack import check_security_stack
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from chirp.middleware.sessions import (
    RedisSessionStore,
    SessionConfig,
    SessionMiddleware,
)
from chirp.middleware.stack import secure_stack
from tests.helpers.redis_capability import ensure_redis_package


class _Route:
    def __init__(self, path: str, methods: set[str]) -> None:
        self.path = path
        self.methods = methods


class _Router:
    def __init__(self, routes: list[_Route]) -> None:
        self.routes = routes


def _mutating_router() -> _Router:
    return _Router([_Route("/save", {"POST"})])


# ---------------------------------------------------------------------------
# Exact classes, exact order
# ---------------------------------------------------------------------------


def test_returns_exact_classes_in_contract_order() -> None:
    cfg = AppConfig(secret_key="x" * 32)
    stack = secure_stack(cfg)
    assert [type(mw).__name__ for mw in stack] == [
        "SessionMiddleware",
        "CSRFMiddleware",
        "SecurityHeadersMiddleware",
    ]
    assert isinstance(stack[0], SessionMiddleware)
    assert isinstance(stack[1], CSRFMiddleware)
    assert isinstance(stack[2], SecurityHeadersMiddleware)


def test_returns_a_plain_list() -> None:
    """A pure list-returning function — the most inspectable/testable shape."""
    cfg = AppConfig(secret_key="x" * 32)
    assert isinstance(secure_stack(cfg), list)


def test_does_not_force_inject_anything() -> None:
    """The helper only builds and returns; it never touches a live app."""
    cfg = AppConfig(secret_key="x" * 32)
    # Two independent calls produce independent, equal-shaped lists — nothing is
    # shared or mutated globally.
    a = secure_stack(cfg)
    b = secure_stack(cfg)
    assert a is not b
    assert [type(mw).__name__ for mw in a] == [type(mw).__name__ for mw in b]


# ---------------------------------------------------------------------------
# Contract conformance: security_stack + csrf_session order
# ---------------------------------------------------------------------------


def test_generated_stack_passes_security_stack_contract_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    stack = secure_stack(cfg)
    assert check_security_stack(_mutating_router(), cfg, stack) == []


def test_generated_stack_passes_csrf_session_order_contract() -> None:
    cfg = AppConfig(secret_key="x" * 32)
    stack = secure_stack(cfg)
    assert check_csrf_session_order(stack) == []


def test_session_before_csrf_in_order() -> None:
    """The CSRF token lives in the session, so Session must precede CSRF."""
    cfg = AppConfig(secret_key="x" * 32)
    names = [type(mw).__name__ for mw in secure_stack(cfg)]
    assert names.index("SessionMiddleware") < names.index("CSRFMiddleware")


# ---------------------------------------------------------------------------
# secure is env-derived, NOT debug-derived
# ---------------------------------------------------------------------------


def _session_secure_resolved(stack: list, env: str) -> bool:
    """Resolve the session middleware's cookie Secure flag for *env*.

    Mirrors the freeze hook (AppCompiler calls ``resolve_secure(env)`` on the
    SessionMiddleware), so this reads the same resolution the runtime applies.
    """
    session_mw = stack[0]
    assert type(session_mw).__name__ == "SessionMiddleware"
    session_mw.resolve_secure(env)
    return session_mw.secure


def test_secure_resolves_true_for_production_even_when_debug_true() -> None:
    """debug=True must NOT force a non-Secure cookie — env is the only signal."""
    cfg = AppConfig(env="production", secret_key="x" * 32, debug=True)
    stack = secure_stack(cfg)
    assert _session_secure_resolved(stack, cfg.env) is True


def test_secure_resolves_true_for_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    stack = secure_stack(cfg)
    assert _session_secure_resolved(stack, cfg.env) is True


def test_secure_resolves_false_for_development_even_when_debug_false() -> None:
    """debug=False must NOT force a Secure cookie in dev — env is the only signal
    (a Secure cookie over local HTTP would log dev users out)."""
    cfg = AppConfig(env="development", debug=False, secret_key="x" * 32)
    stack = secure_stack(cfg)
    assert _session_secure_resolved(stack, cfg.env) is False


def test_configured_secure_is_auto_before_resolution() -> None:
    """The helper leaves secure unset ("auto") so Wave 2 freeze-resolution owns
    it — the single source of truth for cookie-Secure posture."""
    cfg = AppConfig(secret_key="x" * 32)
    session_mw = secure_stack(cfg)[0]
    assert session_mw.configured_secure == "auto"


# ---------------------------------------------------------------------------
# secret_key flows from config
# ---------------------------------------------------------------------------


def test_secret_key_flows_from_config() -> None:
    cfg = AppConfig(secret_key="super-secret-key-1234")
    stack = secure_stack(cfg)
    session_mw = stack[0]
    # The middleware stores the SessionConfig at _config; secret_key must match.
    assert session_mw._config.secret_key == "super-secret-key-1234"


# ---------------------------------------------------------------------------
# Config overrides
# ---------------------------------------------------------------------------


def test_explicit_session_config_is_used_verbatim() -> None:
    cfg = AppConfig(secret_key="x" * 32)
    custom = SessionConfig(secret_key="custom-key-abcdef", cookie_name="my_sess")
    stack = secure_stack(cfg, session=custom)
    assert stack[0]._config is custom
    assert stack[0]._config.cookie_name == "my_sess"


def test_explicit_csrf_config_is_used_verbatim() -> None:
    cfg = AppConfig(secret_key="x" * 32)
    custom = CSRFConfig(field_name="_my_csrf")
    stack = secure_stack(cfg, csrf=custom)
    assert stack[1]._config is custom


def test_explicit_headers_config_is_used_verbatim() -> None:
    cfg = AppConfig(secret_key="x" * 32)
    custom = SecurityHeadersConfig(x_frame_options="SAMEORIGIN")
    stack = secure_stack(cfg, headers=custom)
    assert stack[2].config is custom


@pytest.mark.issue(906)
def test_redis_url_backs_session_with_redis_store() -> None:
    """redis_url (sans explicit session config) routes sessions to Redis."""
    ensure_redis_package()
    cfg = AppConfig(secret_key="x" * 32)
    stack = secure_stack(cfg, redis_url="redis://localhost:6379/0")
    session_mw = stack[0]
    assert isinstance(session_mw._store, RedisSessionStore)
    # secret_key still flows from config into the session config.
    assert session_mw._config.secret_key == "x" * 32


def test_explicit_session_config_overrides_redis_url() -> None:
    """An explicit session config owns its store choice; redis_url is ignored."""
    cfg = AppConfig(secret_key="x" * 32)
    custom = SessionConfig(secret_key="x" * 32)  # default cookie store
    stack = secure_stack(cfg, session=custom, redis_url="redis://localhost:6379/0")
    # Default cookie store — NOT Redis.
    assert not isinstance(stack[0]._store, RedisSessionStore)


# ---------------------------------------------------------------------------
# Optional auth leg
# ---------------------------------------------------------------------------


async def _load_user(user_id: str) -> None:
    return None


def test_no_auth_middleware_by_default() -> None:
    """Omitting auth keeps the original three-leg stack (back-compat)."""
    cfg = AppConfig(secret_key="x" * 32)
    names = [type(mw).__name__ for mw in secure_stack(cfg)]
    assert "AuthMiddleware" not in names


def test_auth_config_inserts_auth_after_session_before_csrf() -> None:
    """auth=AuthConfig(...) adds AuthMiddleware between Session and CSRF, so the
    whole stack is one loop and a CSRF rejection's audit event has the user."""
    from chirp.middleware.auth import AuthConfig

    cfg = AppConfig(secret_key="x" * 32)
    stack = secure_stack(cfg, auth=AuthConfig(load_user=_load_user))
    assert [type(mw).__name__ for mw in stack] == [
        "SessionMiddleware",
        "AuthMiddleware",
        "CSRFMiddleware",
        "SecurityHeadersMiddleware",
    ]


def test_auth_stack_passes_contracts() -> None:
    """The four-leg auth stack still passes security_stack + csrf_session order."""
    from chirp.middleware.auth import AuthConfig

    cfg = AppConfig(env="production", secret_key="x" * 32)
    stack = secure_stack(cfg, auth=AuthConfig(load_user=_load_user))
    assert check_security_stack(_mutating_router(), cfg, stack) == []
    assert check_csrf_session_order(stack) == []

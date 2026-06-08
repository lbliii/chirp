"""Security-stack contract rule (#182).

Unit tests over a stub router + AppConfig + stub middleware, mirroring
test_deploy_preflight.py. The end-to-end wiring proof lives in
test_deploy_nojs_i18n_integration.py.
"""

from chirp.config import AppConfig
from chirp.contracts.rules_security_stack import (
    MUTATING_METHODS,
    check_security_stack,
    is_mutating_route,
)


class _Route:
    def __init__(self, path: str, methods: set[str]) -> None:
        self.path = path
        self.methods = methods


class _PageRoute:
    """Stub mirroring a filesystem PageRoute: GET-only but with form actions."""

    def __init__(self, url_path: str, methods: set[str], actions: tuple) -> None:
        self.url_path = url_path
        self.methods = frozenset(methods)
        self.actions = actions


class _Router:
    def __init__(self, routes: list[_Route]) -> None:
        self.routes = routes


# Stub middleware classes — detection is by class NAME, so these names matter.
class CSRFMiddleware:
    pass


class SessionMiddleware:
    pass


class SecurityHeadersMiddleware:
    pass


def _mutating_router() -> _Router:
    return _Router([_Route("/save", {"POST"})])


def _readonly_router() -> _Router:
    return _Router([_Route("/", {"GET"})])


def _full_stack() -> list[object]:
    return [SessionMiddleware(), CSRFMiddleware(), SecurityHeadersMiddleware()]


# ---------------------------------------------------------------------------
# Canonical predicate
# ---------------------------------------------------------------------------


def test_mutating_methods_set() -> None:
    assert set(MUTATING_METHODS) == {"POST", "PUT", "PATCH", "DELETE"}


def test_is_mutating_route_true_for_each_method() -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert is_mutating_route(_Route("/x", {method})) is True


def test_is_mutating_route_false_for_readonly() -> None:
    assert is_mutating_route(_Route("/", {"GET", "HEAD"})) is False


def test_is_mutating_route_case_insensitive() -> None:
    assert is_mutating_route(_Route("/x", {"post"})) is True


def test_is_mutating_route_no_methods() -> None:
    class _Bare:
        pass

    assert is_mutating_route(_Bare()) is False


def test_is_mutating_route_true_for_get_only_form_action_page() -> None:
    """A GET-only filesystem page with _actions.py form actions is mutating.

    The page mutates state via POST-to-self on the _action field even though
    page.py declares only get(). The canonical predicate must catch this so the
    page is held to the same CSRF/Session bar as a POST route.
    """
    page = _PageRoute("/contacts", {"GET"}, actions=(object(),))
    assert is_mutating_route(page) is True


def test_is_mutating_route_false_for_get_only_page_without_actions() -> None:
    page = _PageRoute("/about", {"GET"}, actions=())
    assert is_mutating_route(page) is False


# ---------------------------------------------------------------------------
# CSRF / Session: env-aware severity
# ---------------------------------------------------------------------------


def test_missing_csrf_session_errors_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_security_stack(_mutating_router(), cfg, [])
    assert "security_stack" in {i.category for i in issues}
    protection = [
        i for i in issues if "CSRFMiddleware" in i.message or "SessionMiddleware" in i.message
    ]
    assert protection
    assert protection[0].severity.name == "ERROR"


def test_missing_csrf_session_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_security_stack(_mutating_router(), cfg, [])
    protection = [i for i in issues if "SessionMiddleware" in i.message]
    assert protection
    assert protection[0].severity.name == "WARNING"


def test_missing_csrf_session_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    issues = check_security_stack(_mutating_router(), cfg, [])
    # Only the SecurityHeaders WARNING may fire; no CSRF/Session issue at all.
    assert not [
        i for i in issues if "CSRFMiddleware" in i.message or "SessionMiddleware" in i.message
    ]


# ---------------------------------------------------------------------------
# SecurityHeaders: WARNING-only, env-independent
# ---------------------------------------------------------------------------


def test_missing_security_headers_warns_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    mws = [SessionMiddleware(), CSRFMiddleware()]
    issues = check_security_stack(_mutating_router(), cfg, mws)
    headers = [i for i in issues if "SecurityHeadersMiddleware" in i.message]
    assert headers
    assert headers[0].severity.name == "WARNING"


def test_missing_security_headers_warns_in_development() -> None:
    cfg = AppConfig(env="development")
    mws = [SessionMiddleware(), CSRFMiddleware()]
    issues = check_security_stack(_mutating_router(), cfg, mws)
    headers = [i for i in issues if "SecurityHeadersMiddleware" in i.message]
    assert headers
    assert headers[0].severity.name == "WARNING"


# ---------------------------------------------------------------------------
# Clean cases
# ---------------------------------------------------------------------------


def test_full_stack_in_production_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_security_stack(_mutating_router(), cfg, _full_stack()) == []


def test_no_mutating_routes_is_clean_even_with_no_stack_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_security_stack(_readonly_router(), cfg, []) == []


def test_development_with_no_mutating_routes_is_clean() -> None:
    cfg = AppConfig(env="development")
    assert check_security_stack(_readonly_router(), cfg, []) == []


def test_rule_does_not_mutate_middleware_list() -> None:
    """The rule must never force-inject middleware — it only reads the list."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    mws: list[object] = []
    check_security_stack(_mutating_router(), cfg, mws)
    assert mws == []


# ---------------------------------------------------------------------------
# Form-action mutating routes (GET-only page + _actions.py)
# ---------------------------------------------------------------------------


def test_form_action_page_flagged_in_production() -> None:
    """A GET-only page backed by _actions.py form actions, no CSRF/Session,
    must ERROR in production exactly like a POST route would.

    The router routes are read-only (GET only); the mutating surface is carried
    by the discovered PageRoute's non-empty `actions`.
    """
    cfg = AppConfig(env="production", secret_key="x" * 32)
    router = _readonly_router()  # only GET routes at the router level
    page = _PageRoute("/contacts", {"GET"}, actions=(object(),))
    issues = check_security_stack(router, cfg, [], discovered_routes=[page])
    protection = [
        i for i in issues if "CSRFMiddleware" in i.message or "SessionMiddleware" in i.message
    ]
    assert protection, "GET-only form-action page should be flagged like a POST route"
    assert protection[0].severity.name == "ERROR"


def test_form_action_page_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    page = _PageRoute("/contacts", {"GET"}, actions=(object(),))
    issues = check_security_stack(_readonly_router(), cfg, [], discovered_routes=[page])
    protection = [i for i in issues if "SessionMiddleware" in i.message]
    assert protection
    assert protection[0].severity.name == "WARNING"


def test_form_action_page_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    page = _PageRoute("/contacts", {"GET"}, actions=(object(),))
    issues = check_security_stack(_readonly_router(), cfg, [], discovered_routes=[page])
    assert not [
        i for i in issues if "CSRFMiddleware" in i.message or "SessionMiddleware" in i.message
    ]


def test_form_action_page_clean_with_full_stack_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    page = _PageRoute("/contacts", {"GET"}, actions=(object(),))
    issues = check_security_stack(_readonly_router(), cfg, _full_stack(), discovered_routes=[page])
    assert issues == []


def test_get_only_page_without_actions_not_flagged_in_production() -> None:
    """A read-only page (no _actions.py) must not be flagged — no false positive."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    page = _PageRoute("/about", {"GET"}, actions=())
    issues = check_security_stack(_readonly_router(), cfg, [], discovered_routes=[page])
    assert issues == []


def test_discovered_routes_defaults_to_none() -> None:
    """The new parameter is optional — existing callers keep working."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    assert check_security_stack(_readonly_router(), cfg, []) == []

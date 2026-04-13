"""Tests for safety contract checks — sse_speculation, csrf_session, middleware_signature."""

from chirp.contracts.rules_safety import (
    check_csrf_session_order,
    check_middleware_signatures,
    check_sse_speculation,
)
from chirp.contracts.types import Severity

# ---------------------------------------------------------------------------
# SSE speculation checks
# ---------------------------------------------------------------------------


class _FakeRoute:
    def __init__(self, path, handler, referenced=False):
        self.path = path
        self.handler = handler
        self.referenced = referenced


class _FakeRouter:
    def __init__(self, routes):
        self.routes = routes


def _sse_handler():
    return "EventStream"


def _normal_handler():
    return "Template"


class TestSSESpeculation:
    def test_sse_without_referenced_warns(self) -> None:
        router = _FakeRouter(
            [
                _FakeRoute("/events", _sse_handler, referenced=False),
            ]
        )
        issues = check_sse_speculation(router)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "sse_speculation"
        assert "/events" in issues[0].message

    def test_sse_with_referenced_ok(self) -> None:
        router = _FakeRouter(
            [
                _FakeRoute("/events", _sse_handler, referenced=True),
            ]
        )
        issues = check_sse_speculation(router)
        assert len(issues) == 0

    def test_normal_route_ok(self) -> None:
        router = _FakeRouter(
            [
                _FakeRoute("/page", _normal_handler, referenced=False),
            ]
        )
        issues = check_sse_speculation(router)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# CSRF / Session middleware checks
# ---------------------------------------------------------------------------


class _FakeCSRFMiddleware:
    """Mimics CSRFMiddleware class name."""


_FakeCSRFMiddleware.__name__ = "CSRFMiddleware"
_FakeCSRFMiddleware.__qualname__ = "CSRFMiddleware"


class _FakeSessionMiddleware:
    """Mimics SessionMiddleware class name."""


_FakeSessionMiddleware.__name__ = "SessionMiddleware"
_FakeSessionMiddleware.__qualname__ = "SessionMiddleware"


# Give them the right class names via type()
CSRFMiddleware = type("CSRFMiddleware", (), {})
SessionMiddleware = type("SessionMiddleware", (), {})


class TestCSRFSessionOrder:
    def test_csrf_without_session_errors(self) -> None:
        issues = check_csrf_session_order([CSRFMiddleware()])
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "csrf_session"
        assert "SessionMiddleware is missing" in issues[0].message

    def test_csrf_with_session_before_ok(self) -> None:
        issues = check_csrf_session_order([SessionMiddleware(), CSRFMiddleware()])
        assert len(issues) == 0

    def test_csrf_before_session_warns(self) -> None:
        issues = check_csrf_session_order([CSRFMiddleware(), SessionMiddleware()])
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "after CSRFMiddleware" in issues[0].message

    def test_no_csrf_no_issues(self) -> None:
        issues = check_csrf_session_order([SessionMiddleware()])
        assert len(issues) == 0

    def test_empty_middleware_no_issues(self) -> None:
        issues = check_csrf_session_order([])
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Middleware signature checks
# ---------------------------------------------------------------------------


class _GoodMiddleware:
    async def __call__(self, request, next):
        return await next(request)


class _SyncMiddleware:
    def __call__(self, request, next):
        return next(request)


class _NoArgMiddleware:
    async def __call__(self):
        pass


class _OneArgMiddleware:
    async def __call__(self, request):
        pass


class TestMiddlewareSignatures:
    def test_good_middleware_ok(self) -> None:
        issues = check_middleware_signatures([_GoodMiddleware()])
        assert len(issues) == 0

    def test_sync_middleware_warns(self) -> None:
        issues = check_middleware_signatures([_SyncMiddleware()])
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "middleware_signature"
        assert "not async" in issues[0].message

    def test_no_arg_middleware_errors(self) -> None:
        issues = check_middleware_signatures([_NoArgMiddleware()])
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "0 positional" in issues[0].message

    def test_one_arg_middleware_errors(self) -> None:
        issues = check_middleware_signatures([_OneArgMiddleware()])
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "1 positional" in issues[0].message

    def test_multiple_middleware_mixed(self) -> None:
        issues = check_middleware_signatures(
            [
                _GoodMiddleware(),
                _SyncMiddleware(),
                _NoArgMiddleware(),
            ]
        )
        assert len(issues) == 2  # sync warning + no-arg error

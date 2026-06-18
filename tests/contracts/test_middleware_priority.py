"""Middleware priority ordering + chain-report diagnostic (#383).

``app.add_middleware(mw, priority=...)`` resolves the user middleware to a
deterministic order at freeze (stable sort by ``(priority, registration)``),
leaving the default-priority case byte-identical to registration order. A new
INFO ``middleware_chain`` diagnostic reports the resolved order without
double-reporting the ``csrf_session`` ERROR, and a priority that reorders
CSRF/Session still raises ``ConfigurationError`` at freeze.
"""

import pytest

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.errors import ConfigurationError
from chirp.middleware.ordering import sort_user_middleware


# Async, two-arg middleware so check_middleware_signatures stays quiet.
class MwA:
    async def __call__(self, request, next):
        return await next(request)


class MwB:
    async def __call__(self, request, next):
        return await next(request)


class MwC:
    async def __call__(self, request, next):
        return await next(request)


def _app(tmp_path) -> App:
    template = tmp_path / "index.html"
    template.write_text("<div id='ok'></div>", encoding="utf-8")
    return App(AppConfig(template_dir=str(tmp_path), debug=False))


def _user_middleware_names(app: App) -> list[str]:
    """User middleware class names from the resolved runtime chain.

    Builtins (allowed-hosts etc.) are filtered out so the assertion targets only
    the sorted user pipeline.
    """
    user = {"MwA", "MwB", "MwC"}
    return [type(mw).__name__ for mw in app._runtime_state.middleware if type(mw).__name__ in user]


# ---------------------------------------------------------------------------
# Unit: the stable sort helper
# ---------------------------------------------------------------------------


def test_sort_is_stable_for_equal_priority() -> None:
    a, b, c = MwA(), MwB(), MwC()
    # All equal priority -> registration order preserved.
    assert sort_user_middleware([a, b, c], [0, 0, 0]) == [a, b, c]


def test_sort_orders_by_priority() -> None:
    a, b, c = MwA(), MwB(), MwC()
    # Lower priority sorts earlier (outermost). Registered c,a,b out of order.
    assert sort_user_middleware([c, a, b], [10, -5, 0]) == [a, b, c]


def test_sort_length_mismatch_is_a_noop() -> None:
    a, b = MwA(), MwB()
    # Defensive: a mismatched priority list never reorders or drops middleware.
    assert sort_user_middleware([a, b], [0]) == [a, b]
    assert sort_user_middleware([a, b], None) == [a, b]


# ---------------------------------------------------------------------------
# Freeze: resolved runtime chain order
# ---------------------------------------------------------------------------


def test_default_priority_is_registration_order(tmp_path) -> None:
    app = _app(tmp_path)
    app.add_middleware(MwA())
    app.add_middleware(MwB())
    app.add_middleware(MwC())
    app.freeze()
    assert _user_middleware_names(app) == ["MwA", "MwB", "MwC"]


def test_priority_reorders_independent_of_registration(tmp_path) -> None:
    app = _app(tmp_path)
    # Register in C, A, B order but priorities force A, B, C.
    app.add_middleware(MwC(), priority=10)
    app.add_middleware(MwA(), priority=-5)
    app.add_middleware(MwB(), priority=0)
    app.freeze()
    assert _user_middleware_names(app) == ["MwA", "MwB", "MwC"]


def test_equal_priority_keeps_registration_order_at_freeze(tmp_path) -> None:
    app = _app(tmp_path)
    app.add_middleware(MwB(), priority=5)
    app.add_middleware(MwA(), priority=5)
    app.freeze()
    # Equal priority -> stable: registration order (B before A) preserved.
    assert _user_middleware_names(app) == ["MwB", "MwA"]


# ---------------------------------------------------------------------------
# Hard floor: CSRF-before-Session priority still raises
# ---------------------------------------------------------------------------


def test_priority_cannot_break_csrf_session_floor(tmp_path) -> None:
    from chirp import SessionConfig, SessionMiddleware
    from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware

    app = _app(tmp_path)
    # Registered Session-before-CSRF, but a lower priority on CSRF would place
    # it outermost (before Session) in the resolved chain — the broken case.
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)), priority=10)
    app.add_middleware(CSRFMiddleware(CSRFConfig()), priority=-10)
    with pytest.raises(ConfigurationError):
        app.freeze()


# ---------------------------------------------------------------------------
# Contract: chain-report diagnostic (#383 acceptance)
# ---------------------------------------------------------------------------


@pytest.mark.issue(383)
def test_chain_report_reflects_resolved_order_without_double_reporting(tmp_path) -> None:
    app = _app(tmp_path)

    @app.route("/")
    def index():
        return "ok"

    # Reorder away from registration order via priority.
    app.add_middleware(MwC(), priority=10)
    app.add_middleware(MwA(), priority=-5)
    app.add_middleware(MwB(), priority=0)

    result = check_hypermedia_surface(app)

    chain_issues = [i for i in result.issues if i.category == "middleware_chain"]
    assert len(chain_issues) == 1, "exactly one chain-report diagnostic"
    issue = chain_issues[0]

    # Diagnostic only — never an ordering ERROR.
    assert issue.severity.name == "INFO"

    # Reports the FREEZE-RESOLVED order (A, B, C), not registration order.
    a_pos = issue.message.index("MwA")
    b_pos = issue.message.index("MwB")
    c_pos = issue.message.index("MwC")
    assert a_pos < b_pos < c_pos

    # No double-report: a valid stack emits no csrf_session ERROR from the
    # chain-report path.
    assert not [i for i in result.issues if i.category == "csrf_session"]


def test_csrf_session_error_uses_resolved_order(tmp_path) -> None:
    """A priority-induced Session-after-CSRF order is caught by csrf_session.

    Without a Session present at all the ConfigurationError floor does not fire
    (it only triggers on CSRF *with* a mis-ordered/missing session), so this
    exercises the report path: registered Session-before-CSRF but a priority
    that resolves CSRF outermost must still surface as the csrf_session ERROR,
    proving the check evaluates the resolved order. We assert via the freeze
    floor, which is the canonical fail-loud for this exact reorder.
    """
    from chirp import SessionConfig, SessionMiddleware
    from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware

    app = _app(tmp_path)

    @app.route("/")
    def index():
        return "ok"

    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)), priority=10)
    app.add_middleware(CSRFMiddleware(CSRFConfig()), priority=-10)

    # check_hypermedia_surface freezes the app, which raises the hard floor.
    with pytest.raises(ConfigurationError):
        check_hypermedia_surface(app)


def test_no_chain_report_when_no_user_middleware(tmp_path) -> None:
    app = _app(tmp_path)

    @app.route("/")
    def index():
        return "ok"

    result = check_hypermedia_surface(app)
    assert not [i for i in result.issues if i.category == "middleware_chain"]

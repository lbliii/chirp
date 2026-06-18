"""SSE auth-context contract rules: sse_auth_gate + sse_context.

Unit tests build a real handler (so ``inspect.getsource`` works) and a stub
router; middleware is detected by class NAME, so stub class names matter. The
orchestrator-wiring and shipped-example guards live at the bottom and mirror
test_auth_meta.py / test_cookie_secure.py.

Both rules statically resolve an EventStream route's generator in TWO scopes:
an inline nested ``async def`` inside the handler, AND a module-level
``async def`` passed as ``EventStream(gen())`` (via the handler ``__globals__``).
A generator built by any other indirection is a documented blind spot — never
a false ERROR.
"""

import pytest

from chirp import EventStream, Fragment
from chirp.config import AppConfig
from chirp.contracts.rules_sse import check_sse_auth_gate, check_sse_context
from chirp.middleware.auth import current_user, get_user

# ---------------------------------------------------------------------------
# Stubs. Detection is by class NAME.
# ---------------------------------------------------------------------------


class AuthMiddleware:
    pass


class SessionMiddleware:
    pass


class _Route:
    def __init__(self, path: str, handler) -> None:
        self.path = path
        self.handler = handler


class _Router:
    def __init__(self, routes: list[_Route]) -> None:
        self.routes = routes


def _router(handler, path: str = "/events") -> _Router:
    return _Router([_Route(path, handler)])


# ---------------------------------------------------------------------------
# Handlers under test. Defined at module scope so inspect.getsource works.
# ---------------------------------------------------------------------------


def handler_user_in_loop():
    """EventStream whose generator reads the user inside a long-lived loop."""

    async def generate():
        while True:
            user = get_user()
            yield Fragment("page.html", "row", user=user)

    return EventStream(generate())


def handler_current_user_in_async_for():
    """current_user() inside an `async for` long-lived pump."""

    async def generate():
        async for msg in _bus():  # noqa: F821 - illustrative, never executed
            yield Fragment("page.html", "row", who=current_user(), msg=msg)

    return EventStream(generate())


def handler_user_top_level_only():
    """User read ONCE at generator top-level (short-lived), not in any loop."""

    async def generate():
        user = get_user()
        yield Fragment("page.html", "row", user=user)

    return EventStream(generate())


def handler_global_state_in_loop():
    """Long-lived loop that reads GLOBAL state, never the user (shipped-example shape)."""

    async def generate():
        while True:
            yield Fragment("page.html", "row", data=_global_data())  # noqa: F821

    return EventStream(generate())


# Module-level generator (NOT nested) — the SCOPE-HONESTY case the check must
# resolve via __globals__.
async def _module_level_gen():
    while True:
        yield Fragment("page.html", "row", user=get_user())


def handler_module_level_gen():
    return EventStream(_module_level_gen())


def handler_not_eventstream():
    """A plain handler that calls get_user() but returns no EventStream."""
    user = get_user()
    return Fragment("page.html", "row", user=user)


# ===========================================================================
# CHECK 1 — sse_auth_gate
# ===========================================================================


def test_user_read_no_authmw_errors_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_user_in_loop), cfg, [])
    gate = [i for i in issues if i.category == "sse_auth_gate"]
    assert gate, "sse_auth_gate did not fire"
    assert gate[0].severity.name == "ERROR"
    assert "/events" in gate[0].message


def test_user_read_no_authmw_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_user_in_loop), cfg, [])
    gate = next(i for i in issues if i.category == "sse_auth_gate")
    assert gate.severity.name == "WARNING"


def test_user_read_no_authmw_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    issues = check_sse_auth_gate(_router(handler_user_in_loop), cfg, [])
    assert issues == []


def test_authmw_present_is_clean() -> None:
    """AuthMiddleware wired -> the user resolves -> nothing to flag."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_user_in_loop), cfg, [AuthMiddleware()])
    assert issues == []


def test_authmw_present_among_others_is_clean() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(
        _router(handler_user_in_loop), cfg, [SessionMiddleware(), AuthMiddleware()]
    )
    assert issues == []


def test_current_user_accessor_is_flagged() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_current_user_in_async_for), cfg, [])
    assert any(i.category == "sse_auth_gate" and i.severity.name == "ERROR" for i in issues)


def test_top_level_user_read_is_flagged_by_gate() -> None:
    """sse_auth_gate fires on ANY user read (loop or not) — a top-level read
    still resolves to AnonymousUser without AuthMiddleware."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_user_top_level_only), cfg, [])
    assert any(i.category == "sse_auth_gate" for i in issues)


def test_global_state_eventstream_not_flagged() -> None:
    """An EventStream that reads only GLOBAL state (no user) is never flagged —
    the shipped chat/kanban/dashboard generator shape."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_global_state_in_loop), cfg, [])
    assert issues == []


def test_non_eventstream_handler_not_flagged() -> None:
    """A plain handler that calls get_user() but returns no EventStream is not
    an SSE route — never flagged by this rule."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_not_eventstream), cfg, [])
    assert issues == []


def test_module_level_generator_resolved_via_globals() -> None:
    """SCOPE HONESTY: a module-level `async def gen()` passed as
    EventStream(gen()) is resolved via the handler __globals__ and flagged."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_auth_gate(_router(handler_module_level_gen), cfg, [])
    assert any(i.category == "sse_auth_gate" and i.severity.name == "ERROR" for i in issues), (
        "module-level generator user-read was missed (globals resolution failed)"
    )


# ===========================================================================
# CHECK 2 — sse_context (post-fix semantic nudge)
# ===========================================================================


def test_user_in_long_lived_loop_warns_in_production() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_user_in_loop), cfg)
    ctx = [i for i in issues if i.category == "sse_context"]
    assert ctx, "sse_context did not fire for a user read in a long-lived loop"
    assert ctx[0].severity.name == "WARNING", "sse_context must be WARNING, never ERROR"


def test_user_in_async_for_warns() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_current_user_in_async_for), cfg)
    assert any(i.category == "sse_context" and i.severity.name == "WARNING" for i in issues)


def test_sse_context_warns_in_staging() -> None:
    cfg = AppConfig(env="staging", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_user_in_loop), cfg)
    ctx = next(i for i in issues if i.category == "sse_context")
    assert ctx.severity.name == "WARNING"


def test_sse_context_silent_in_development() -> None:
    cfg = AppConfig(env="development")
    issues = check_sse_context(_router(handler_user_in_loop), cfg)
    assert issues == []


def test_sse_context_never_error() -> None:
    """The pattern WORKS — sse_context must NEVER be ERROR even in production."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_user_in_loop), cfg)
    assert all(i.severity.name != "ERROR" for i in issues if i.category == "sse_context")


def test_top_level_user_read_not_nudged_by_context() -> None:
    """A short-lived top-level user read (outside any loop) is NOT a staleness
    caveat — it resolves once and the stream ends. Not nudged by sse_context."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_user_top_level_only), cfg)
    assert not [i for i in issues if i.category == "sse_context"]


def test_global_state_loop_not_nudged() -> None:
    """A long-lived loop reading only GLOBAL state is not auth-sensitive — not
    nudged (the shipped-example shape)."""
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_global_state_in_loop), cfg)
    assert not [i for i in issues if i.category == "sse_context"]


def test_module_level_generator_loop_nudged() -> None:
    cfg = AppConfig(env="production", secret_key="x" * 32)
    issues = check_sse_context(_router(handler_module_level_gen), cfg)
    assert any(i.category == "sse_context" and i.severity.name == "WARNING" for i in issues)


# ===========================================================================
# Orchestrator wiring + --deploy escalation (mirrors test_auth_meta.py).
# ===========================================================================


@pytest.mark.issue(220)
def test_sse_auth_gate_fires_through_orchestrator(tmp_path) -> None:
    from chirp import App
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "page.html").write_text(
        "{% block row %}<div id='r'></div>{% endblock %}", encoding="utf-8"
    )
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/events", referenced=True)
    def events():  # pragma: no cover - never invoked
        async def generate():
            while True:
                yield Fragment("page.html", "row", user=get_user())

        return EventStream(generate())

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "sse_auth_gate"]
    assert any(i.severity.name == "ERROR" for i in issues), (
        "sse_auth_gate did not fire through check_hypermedia_surface"
    )


@pytest.mark.issue(220)
def test_sse_auth_gate_clean_through_orchestrator_with_authmw(tmp_path) -> None:
    from chirp import App
    from chirp.contracts import check_hypermedia_surface
    from chirp.middleware.auth import AuthConfig
    from chirp.middleware.auth import AuthMiddleware as RealAuthMiddleware
    from chirp.middleware.sessions import SessionConfig
    from chirp.middleware.sessions import SessionMiddleware as RealSessionMiddleware

    (tmp_path / "page.html").write_text(
        "{% block row %}<div id='r'></div>{% endblock %}", encoding="utf-8"
    )
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

    @app.route("/events", referenced=True)
    def events():  # pragma: no cover - never invoked
        async def generate():
            while True:
                yield Fragment("page.html", "row", user=get_user())

        return EventStream(generate())

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "sse_auth_gate"]
    assert not issues, "sse_auth_gate should be clean when AuthMiddleware is registered"


@pytest.mark.issue(220)
def test_sse_context_fires_through_orchestrator(tmp_path) -> None:
    from chirp import App
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "page.html").write_text(
        "{% block row %}<div id='r'></div>{% endblock %}", encoding="utf-8"
    )
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/events", referenced=True)
    def events():  # pragma: no cover - never invoked
        async def generate():
            while True:
                yield Fragment("page.html", "row", user=get_user())

        return EventStream(generate())

    issues = [i for i in check_hypermedia_surface(app).issues if i.category == "sse_context"]
    assert any(i.severity.name == "WARNING" for i in issues), (
        "sse_context did not fire through check_hypermedia_surface"
    )


@pytest.mark.issue(220)
def test_deploy_posture_escalates_sse_auth_gate(tmp_path) -> None:
    """A dev app passes sse_auth_gate in dev posture but ERRORs under deploy
    posture, while the real config keeps env='development'."""
    from chirp import App
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "page.html").write_text(
        "{% block row %}<div id='r'></div>{% endblock %}", encoding="utf-8"
    )
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
            secret_key="x" * 32,
        )
    )

    @app.route("/events", referenced=True)
    def events():  # pragma: no cover - never invoked
        async def generate():
            while True:
                yield Fragment("page.html", "row", user=get_user())

        return EventStream(generate())

    dev = [i for i in check_hypermedia_surface(app).issues if i.category == "sse_auth_gate"]
    assert not dev, "sse_auth_gate should be silent in development posture"

    deploy = [
        i
        for i in check_hypermedia_surface(app, deploy=True).issues
        if i.category == "sse_auth_gate"
    ]
    assert deploy, "sse_auth_gate did not escalate under deploy posture"
    assert any(i.severity.name == "ERROR" for i in deploy)
    assert app.config.env == "development"


# ===========================================================================
# Shipped-example guard: chat/kanban/dashboard/lucky_cat SSE generators read
# GLOBAL state (not the user) inside their generator, so neither rule fires.
# ===========================================================================


@pytest.mark.issue(220)
def test_shipped_global_state_example_clean(tmp_path) -> None:
    """A real app whose SSE generator reads global state (the chat/kanban
    shape) is clean under both rules even in production."""
    from chirp import App
    from chirp.contracts import check_hypermedia_surface

    (tmp_path / "page.html").write_text(
        "{% block row %}<div id='r'></div>{% endblock %}", encoding="utf-8"
    )
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    _messages = ["a", "b"]

    @app.route("/events", referenced=True)
    def events():  # pragma: no cover - never invoked
        async def generate():
            while True:
                yield Fragment("page.html", "row", data=_messages)

        return EventStream(generate())

    issues = [
        i
        for i in check_hypermedia_surface(app).issues
        if i.category in ("sse_auth_gate", "sse_context")
    ]
    assert not issues, f"global-state SSE example was wrongly flagged: {issues}"

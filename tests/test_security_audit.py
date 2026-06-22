"""Tests for security audit events."""

from dataclasses import dataclass

import pytest

from chirp import App
from chirp.middleware.audit import AuditConfig, AuditMiddleware
from chirp.middleware.auth import AuthConfig, AuthMiddleware, login, logout
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.security.audit import SecurityEvent, emit_security_event, set_security_event_sink
from chirp.testing import TestClient


def _http_events(events: list[SecurityEvent]) -> list[SecurityEvent]:
    return [e for e in events if e.name == "http.request"]


@dataclass(frozen=True, slots=True)
class _User:
    id: str
    is_authenticated: bool = True


async def _load_user(user_id: str) -> _User | None:
    if user_id == "u1":
        return _User(id="u1")
    return None


@pytest.mark.anyio
async def test_emit_without_sink_is_noop() -> None:
    set_security_event_sink(None)
    emit_security_event("auth.test")


@pytest.mark.anyio
async def test_login_logout_emit_security_events() -> None:
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load_user)))

        @app.route("/do-login")
        def do_login():
            login(_User(id="u1"))
            return "ok"

        @app.route("/do-logout")
        def do_logout():
            logout()
            return "ok"

        async with TestClient(app) as client:
            r1 = await client.get("/do-login")
            cookie = None
            for name, value in r1.headers:
                if name == "set-cookie" and value.startswith("chirp_session="):
                    cookie = value.split(";")[0].partition("=")[2]
                    break
            assert cookie is not None
            await client.get("/do-logout", headers={"Cookie": f"chirp_session={cookie}"})
    finally:
        set_security_event_sink(None)

    names = [event.name for event in events]
    assert "auth.login.success" in names
    assert "auth.logout.success" in names


@pytest.mark.anyio
async def test_csrf_missing_emits_event() -> None:
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(CSRFMiddleware())

        @app.route("/submit", methods=["POST"])
        async def submit(request):
            _ = await request.form()
            return "ok"

        @app.route("/touch")
        def touch():
            session = get_session()
            session["x"] = 1
            return "ok"

        async with TestClient(app) as client:
            r1 = await client.get("/touch")
            cookie = None
            for name, value in r1.headers:
                if name == "set-cookie" and value.startswith("chirp_session="):
                    cookie = value.split(";")[0].partition("=")[2]
                    break
            assert cookie is not None
            response = await client.post(
                "/submit",
                body=b"a=1",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": f"chirp_session={cookie}",
                },
            )
            assert response.status == 403
    finally:
        set_security_event_sink(None)

    assert any(event.name == "csrf.reject.missing" for event in events)


# -- AuditMiddleware (#369) --


@pytest.mark.anyio
@pytest.mark.issue(369)
async def test_audit_mutating_post_emits_http_request_event() -> None:
    """Acceptance: a mutating POST emits exactly one http.request audit event
    carrying status_code, source_ip, and user_agent through the sink."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(AuditMiddleware(AuditConfig(level="metadata")))

        @app.route("/submit", methods=["POST"])
        async def submit(request):
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"a=1",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "pytest-agent/1.0",
                },
            )
            assert response.status == 200
    finally:
        set_security_event_sink(None)

    http = _http_events(events)
    assert len(http) == 1
    event = http[0]
    assert event.name == "http.request"
    assert event.method == "POST"
    assert event.path == "/submit"
    assert event.details["status_code"] == 200
    # source_ip is the trusted-proxy-corrected client (TestClient sets a client
    # tuple); it is always present and never the raw X-Forwarded-For.
    assert isinstance(event.details["source_ip"], str)
    assert event.details["source_ip"]
    assert event.details["user_agent"] == "pytest-agent/1.0"
    # No body capture at metadata level.
    assert "body" not in event.details


@pytest.mark.anyio
async def test_audit_disabled_by_default_emits_nothing() -> None:
    """AuditConfig() defaults to level='none' and emits no http.request events."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(AuditMiddleware())  # default = level="none"

        @app.route("/submit", methods=["POST"])
        async def submit(request):
            return "ok"

        async with TestClient(app) as client:
            await client.post("/submit", body=b"a=1")
    finally:
        set_security_event_sink(None)

    assert _http_events(events) == []


@pytest.mark.anyio
async def test_audit_non_audited_method_emits_nothing() -> None:
    """A GET is not in the default MUTATING_METHODS audited set — no event."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(AuditMiddleware(AuditConfig(level="metadata")))

        @app.route("/show")
        async def show(request):
            return "ok"

        async with TestClient(app) as client:
            await client.get("/show")
    finally:
        set_security_event_sink(None)

    assert _http_events(events) == []


@pytest.mark.anyio
async def test_audit_redacts_sensitive_form_keys() -> None:
    """redact_keys masks password/token values in the captured request body."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(AuditMiddleware(AuditConfig(level="request")))

        @app.route("/login", methods=["POST"])
        async def do_login(request):
            # Handler consumes the body; the middleware reads it from cache.
            await request.form()
            return "ok"

        async with TestClient(app) as client:
            await client.post(
                "/login",
                body=b"username=alice&password=hunter2&token=abc123",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    finally:
        set_security_event_sink(None)

    http = _http_events(events)
    assert len(http) == 1
    body = http[0].details["body"]
    assert isinstance(body, str)
    assert "alice" in body  # non-sensitive value preserved
    assert "hunter2" not in body  # password masked
    assert "abc123" not in body  # token masked
    assert "REDACTED" in body


@pytest.mark.anyio
async def test_audit_redact_patterns_mask_matches() -> None:
    """redact_patterns masks any matching substring (e.g. card-like digits)."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(
            AuditMiddleware(AuditConfig(level="request", redact_patterns=(r"\d{16}",)))
        )

        @app.route("/pay", methods=["POST"])
        async def pay(request):
            await request.form()
            return "ok"

        async with TestClient(app) as client:
            await client.post(
                "/pay",
                body=b"card=4111111111111111&note=ok",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    finally:
        set_security_event_sink(None)

    http = _http_events(events)
    assert len(http) == 1
    body = http[0].details["body"]
    assert "4111111111111111" not in body
    assert "REDACTED" in body


@pytest.mark.anyio
async def test_audit_streaming_response_is_metadata_only_body_never_drained() -> None:
    """A mutating POST resolving to a streaming response (EventStream ->
    SSEResponse) downgrades to metadata-only and the request body is provably
    never drained by the middleware — the request's body cache is still empty
    after the middleware ran, so a later consumer (the stream drain) can read it.
    """
    from chirp import EventStream

    events: list[SecurityEvent] = []
    captured_requests: list[object] = []
    set_security_event_sink(events.append)
    try:
        # level="request" would normally capture the body; the streaming
        # downgrade must override that and skip body capture entirely.
        app = App()
        app.add_middleware(AuditMiddleware(AuditConfig(level="request")))

        @app.route("/stream", methods=["POST"])
        def stream_route(request):
            captured_requests.append(request)

            async def gen():
                yield "tick"

            return EventStream(gen())

        async with TestClient(app) as client:
            captured = await client.request_chunks(
                "POST",
                "/stream",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=b"a=streamed",
            )
            assert captured.status == 200
    finally:
        set_security_event_sink(None)

    http = _http_events(events)
    assert len(http) == 1
    event = http[0]
    # Metadata is still present.
    assert event.details["status_code"] == 200
    assert isinstance(event.details["source_ip"], str)
    # Body was withheld due to the streaming downgrade — never drained.
    assert event.details["body"] is None
    assert event.details["body_omitted"] == "streaming_response"
    # Proof the middleware NEVER drained the body: the request body cache was
    # never populated by AuditMiddleware (it would be present had body() been
    # called). The handler never read it either, so it remains available to the
    # stream drain / any downstream consumer.
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert "_body" not in request._cache  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_audit_resolves_authenticated_user_id() -> None:
    """With AuthMiddleware upstream, the audit trail records the resolved user."""
    events: list[SecurityEvent] = []
    set_security_event_sink(events.append)
    try:
        app = App()
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load_user)))
        app.add_middleware(AuditMiddleware(AuditConfig(level="metadata")))

        @app.route("/act", methods=["POST"])
        async def act(request):
            return "ok"

        @app.route("/login-now")
        def login_now():
            login(_User(id="u1"))
            return "ok"

        async with TestClient(app) as client:
            r1 = await client.get("/login-now")
            cookie = None
            for name, value in r1.headers:
                if name == "set-cookie" and value.startswith("chirp_session="):
                    cookie = value.split(";")[0].partition("=")[2]
                    break
            assert cookie is not None
            await client.post("/act", body=b"x=1", headers={"Cookie": f"chirp_session={cookie}"})
    finally:
        set_security_event_sink(None)

    http = _http_events(events)
    assert len(http) == 1
    assert http[0].user_id == "u1"


@pytest.mark.anyio
async def test_invalid_level_raises() -> None:
    """AuditConfig rejects an unknown verbosity level at construction."""
    with pytest.raises(ValueError, match="level must be one of"):
        AuditConfig(level="verbose")


def test_secure_stack_appends_audit_as_outermost_leg() -> None:
    """secure_stack(audit=...) appends AuditMiddleware as the last/outermost
    leg, after SecurityHeadersMiddleware, and preserves the contract order."""
    from chirp.config import AppConfig
    from chirp.middleware.stack import secure_stack

    config = AppConfig(secret_key="test-secret")
    stack = secure_stack(config, audit=AuditConfig(level="metadata"))
    names = [type(mw).__name__ for mw in stack]
    assert names == [
        "SessionMiddleware",
        "CSRFMiddleware",
        "SecurityHeadersMiddleware",
        "AuditMiddleware",
    ]
    # Session before CSRF (csrf_session order contract) still holds.
    assert names.index("SessionMiddleware") < names.index("CSRFMiddleware")

    # Without audit, no AuditMiddleware leg is added.
    plain = [type(mw).__name__ for mw in secure_stack(config)]
    assert "AuditMiddleware" not in plain

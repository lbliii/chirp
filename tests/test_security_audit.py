"""Tests for security audit events."""

from dataclasses import dataclass

import pytest

from chirp.app import App
from chirp.middleware.auth import AuthConfig, AuthMiddleware, login, logout
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.security.audit import SecurityEvent, emit_security_event, set_security_event_sink
from chirp.testing import TestClient


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

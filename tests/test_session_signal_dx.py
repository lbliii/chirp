"""Epic D — session signal seeding, signal_bind, SignalEmit, DevTools trace."""

from __future__ import annotations

import base64
import json
import uuid

import pytest

from chirp import App, AppConfig
from chirp.contracts.rules_signals import (
    check_signal_bindings,
    check_signal_connect_budget,
)
from chirp.contracts.types import Severity
from chirp.http.headers import Headers
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware import auth as auth_module
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.session_signals import SessionSignalConfig, SessionSignalMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.realtime.emit_bridge import clear_emit_impl, register_emit_impl
from chirp.realtime.signal_globals import make_signal_globals
from chirp.realtime.signal_trace import encode_signal_emit_trace, get_signal_emit_trace
from chirp.realtime.signals import SignalSpec
from chirp.server.negotiation import negotiate
from chirp.templating.returns import SignalEmit


class _User:
    __slots__ = ("id", "is_authenticated")

    def __init__(self, user_id: str = "u1", *, authed: bool = True) -> None:
        self.id = user_id
        self.is_authenticated = authed


async def _load_user(user_id: str) -> _User | None:
    return _User(user_id) if user_id else None


async def _noop_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(*, htmx: bool = False) -> Request:
    headers = [("hx-request", "true")] if htmx else []
    return Request(
        method="POST",
        path="/deposit",
        headers=Headers(tuple(headers)),
        query={},
        path_params={},
        http_version="1.1",
        server=("test", 80),
        client=("127.0.0.1", 12345),
        cookies={},
        request_id=str(uuid.uuid4()),
        _receive=_noop_receive,
    )


def _make_signal_app() -> App:
    app = App(AppConfig(template_dir=None, debug=False, skip_contract_checks=True))

    @app.signal("balance", audience="session")
    def balance():
        if False:
            yield

    app.freeze()
    return app


class TestSessionSignalMiddleware:
    @pytest.mark.issue(407)
    @pytest.mark.asyncio
    async def test_seeds_session_signals_for_authenticated_user(self) -> None:
        app = _make_signal_app()
        mw = SessionSignalMiddleware(
            SessionSignalConfig(
                app=app,
                audience_key=lambda: "visitor-1",
                seeds={"balance": lambda: 100},
            )
        )
        req = _request()

        async def next_handler(request: Request) -> Response:
            registry = app._mutable_state.signal_registry
            assert registry is not None
            assert registry.current_rendered("balance", audience_key="visitor-1") == "100"
            return Response(body="ok")

        token = auth_module._user_var.set(_User())
        try:
            response = await mw(req, next_handler)
        finally:
            auth_module._user_var.reset(token)
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_anonymous_clears_audience(self) -> None:
        app = _make_signal_app()
        mw = SessionSignalMiddleware(
            SessionSignalConfig(
                app=app,
                audience_key=lambda: "visitor-1",
                seeds={"balance": lambda: 100},
            )
        )
        req = _request()
        seen_aud = ""

        async def next_handler(request: Request) -> Response:
            from chirp.realtime.signal_globals import current_signal_audience

            nonlocal seen_aud
            seen_aud = current_signal_audience()
            return Response(body="ok")

        token = auth_module._user_var.set(_User(authed=False))
        try:
            await mw(req, next_handler)
        finally:
            auth_module._user_var.reset(token)
        assert seen_aud == ""


class TestSignalBind:
    @pytest.mark.issue(408)
    def test_signal_bind_is_contract_aware(self) -> None:
        sources = {
            "_layout.html": "{{ signal_connect() }}",
            "page.html": '<ul id="notif-list" {{ signal_bind("notifications") }}></ul>',
        }
        issues = check_signal_bindings(sources, frozenset({"notifications"}))
        assert not [i for i in issues if i.category == "signal_dead_binding"]
        assert not [i for i in issues if i.category == "signal_raw_sse_swap"]

    def test_signal_bind_emits_attrs(self) -> None:
        from chirp.realtime.signals import SignalRegistry

        reg = SignalRegistry()
        reg.register(SignalSpec(name="x"))
        bind = make_signal_globals(reg)["signal_bind"]
        assert 'sse-swap="x"' in str(bind("x"))


class TestSignalEmit:
    @pytest.mark.issue(409)
    def test_negotiate_emits_and_returns_204(self) -> None:
        app = _make_signal_app()
        register_emit_impl(app.emit)
        try:
            from chirp.context import request_var
            from chirp.realtime.signal_globals import set_signal_audience

            req = _request(htmx=True)
            req_token = request_var.set(req)
            aud_token = set_signal_audience("visitor-1")
            try:
                response = negotiate(SignalEmit(("balance", 777)), request=req)
            finally:
                from chirp.realtime.signal_globals import reset_signal_audience

                reset_signal_audience(aud_token)
                request_var.reset(req_token)
            assert response.status == 204
            registry = app._mutable_state.signal_registry
            assert registry is not None
            assert registry.cached_value("balance", audience_key="visitor-1") == 777
            trace = get_signal_emit_trace(req)
            assert len(trace) == 1
            assert trace[0].name == "balance"
        finally:
            clear_emit_impl()

    def test_requires_at_least_one_pair(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            SignalEmit()


class TestSignalConnectBudget:
    @pytest.mark.issue(405)
    def test_multiple_templates_with_connect_is_info(self) -> None:
        sources = {
            "_layout.html": "{{ signal_connect() }}",
            "page.html": '{{ signal_connect() }}<span sse-swap="x"></span>',
        }
        issues = check_signal_connect_budget(sources)
        assert any(i.category == "signal_connect_budget" for i in issues)
        assert all(i.severity is Severity.INFO for i in issues)


class TestSignalEmitTraceHeader:
    @pytest.mark.issue(411)
    def test_encode_roundtrip(self) -> None:
        from chirp.context import request_var
        from chirp.realtime.signal_trace import record_signal_emit

        req = _request()
        token = request_var.set(req)
        try:
            record_signal_emit("balance", audience_key="k1")
            encoded = encode_signal_emit_trace(get_signal_emit_trace(req))
        finally:
            request_var.reset(token)
        payload = json.loads(base64.b64decode(encoded))
        assert payload == [{"name": "balance", "audience_key": "k1", "scope": "session"}]

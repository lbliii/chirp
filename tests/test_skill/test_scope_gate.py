"""Proof for #971 — skill.tool scopes via enforce_auth; 403 → JSON-RPC; audit."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.context import request_var
from chirp.errors import ToolAuthError
from chirp.http.request import Request
from chirp.middleware.auth import _user_var
from chirp.security.audit import SecurityEvent, set_security_event_sink
from chirp.skill import Envelope, Skill, use_skill
from chirp.tools.events import ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import compile_tools


@dataclass(frozen=True, slots=True)
class _MachineClient:
    """Token client with scopes — satisfies ClientWithScopes."""

    id: str
    scopes: frozenset[str]
    is_authenticated: bool = True


@dataclass(frozen=True, slots=True)
class _HumanUser:
    """Human with permissions but no scopes protocol."""

    id: str
    permissions: frozenset[str]
    is_authenticated: bool = True


def _fake_request(*, path: str = "/mcp") -> Request:
    async def receive():
        return {"type": "http.disconnect"}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"authorization", b"Bearer tok")],
            "query_string": b"",
        },
        receive,
    )


def _mcp_call_request(tool: str, arguments: dict) -> Request:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    raw = json.dumps(body).encode()
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive,
    )


@pytest.mark.issue(971)
class TestSkillScopeGateIssue971:
    @pytest.fixture(autouse=True)
    def _events_sink(self):
        events: list[SecurityEvent] = []
        set_security_event_sink(events.append)
        self.events = events
        try:
            yield events
        finally:
            set_security_event_sink(None)

    def _mount_scoped_skill(self) -> App:
        private = Ed25519PrivateKey.generate()
        skill = Skill(
            "hooks",
            version="1.0.0",
            private_key=private,
            key_id="hooks-1",
        )

        @skill.tool("ping", description="Scoped ping", scopes=("webhook:write",))
        def ping(msg: str) -> str:
            return f"pong:{msg}"

        app = App()
        app.register_scope("webhook:write")

        @app.route("/")
        def index() -> str:
            return "ok"

        use_skill(app, skill)
        app._ensure_frozen()
        return app

    async def test_scoped_client_passes(self) -> None:
        app = self._mount_scoped_skill()
        client = _MachineClient(id="mw", scopes=frozenset({"webhook:write"}))
        req = _fake_request()
        req_tok = request_var.set(req)
        user_tok = _user_var.set(client)
        try:
            result = await app.tools.call_tool("ping", {"msg": "hi"})
        finally:
            request_var.reset(req_tok)
            _user_var.reset(user_tok)

        assert isinstance(result, Envelope)
        assert result.payload == "pong:hi"
        assert not any(e.name == "authz.scope.denied" for e in self.events)

    async def test_unscoped_client_denied_and_audited(self) -> None:
        app = self._mount_scoped_skill()
        client = _MachineClient(id="mr", scopes=frozenset({"webhook:read"}))
        req = _fake_request()
        req_tok = request_var.set(req)
        user_tok = _user_var.set(client)
        try:
            with pytest.raises(ToolAuthError) as exc:
                await app.tools.call_tool("ping", {"msg": "nope"})
        finally:
            request_var.reset(req_tok)
            _user_var.reset(user_tok)

        assert exc.value.status == 403
        assert exc.value.detail == "Forbidden"
        denied = [e for e in self.events if e.name == "authz.scope.denied"]
        assert len(denied) == 1
        assert denied[0].details == {"missing": ["webhook:write"]}

    async def test_unscoped_maps_403_to_jsonrpc(self) -> None:
        private = Ed25519PrivateKey.generate()
        skill = Skill("hooks", version="1.0.0", private_key=private, key_id="hooks-1")

        @skill.tool("ping", scopes=("webhook:write",))
        def ping(msg: str) -> str:
            return f"pong:{msg}"

        app = App()
        use_skill(app, skill)
        pending = [
            (p.name, p.description, p.handler, p.approval_required) for p in app._pending_tools
        ]
        registry = compile_tools(pending, ToolEventBus())

        client = _HumanUser(id="h", permissions=frozenset({"admin"}))
        req = _mcp_call_request("ping", {"msg": "x"})
        req_tok = request_var.set(req)
        user_tok = _user_var.set(client)
        try:
            response = await handle_mcp_request(req, registry)
        finally:
            request_var.reset(req_tok)
            _user_var.reset(user_tok)

        assert response.status == 200
        body = json.loads(response.body_bytes)
        assert "error" in body
        assert body["error"]["code"] == -32603
        assert body["error"]["message"] == "Forbidden"
        assert any(e.name == "authz.scope.denied" for e in self.events)

"""Canonical authorization errors survive traced HTTP and MCP dispatch (#1063)."""

import json

import pytest

from chirp import App
from chirp.errors import HTTPError, ToolAuthError
from chirp.testing import TestClient
from chirp.tools.events import ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import compile_tools
from tests.test_tools.test_mcp_handler import _make_request, _routing_headers, _stateless_meta


@pytest.mark.issue(1063)
@pytest.mark.parametrize(("status", "detail"), [(401, "Unauthorized"), (403, "Forbidden")])
async def test_same_authorization_gate_works_over_http_and_mcp(status: int, detail: str) -> None:
    error = HTTPError(status, detail)
    app = App()

    @app.route("/gate")
    @app.tool("gate", description="Authorization gate")
    async def gate() -> str:
        raise error

    @app.error(status)
    def denied(request, exc):
        from chirp.http.response import Response

        assert exc is error
        return Response(body=exc.detail, status=exc.status)

    async with TestClient(app) as client:
        response = await client.get("/gate")
        assert response.status == status
        assert response.text == detail
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "gate", "arguments": {}, "_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/call", name="gate"),
        )
        assert response.status == 200
        assert json.loads(response.text)["error"] == {"code": -32603, "message": detail}


@pytest.mark.issue(1063)
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (HTTPError(401), "Unauthorized"),
        (HTTPError(403), "Forbidden"),
        (ToolAuthError(status=403, detail="Access denied"), "Access denied"),
        (PermissionError("Access denied"), "Tool execution error: Access denied"),
        (RuntimeError("internal-secret"), "Tool execution error"),
        (TypeError("internal-secret"), "Tool execution error"),
        (KeyError("internal-secret"), "Tool execution error"),
    ],
)
async def test_mcp_errors_do_not_expose_traceback(error: Exception, message: str, caplog) -> None:
    def gate() -> None:
        raise error

    registry = compile_tools([("gate", "Authorization gate", gate)], ToolEventBus())
    response = await handle_mcp_request(
        _make_request(
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "gate", "arguments": {}, "_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/call", name="gate"),
        ),
        registry,
    )
    body = response.body_bytes.decode()
    assert json.loads(body)["error"] == {"code": -32603, "message": message}
    assert "internal-secret" not in body
    assert "Traceback" not in body
    assert "FrozenInstanceError" not in body
    if isinstance(error, RuntimeError):
        assert caplog.records[-1].exc_info[1] is error

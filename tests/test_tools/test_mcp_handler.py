"""Tests for chirp.tools.handler — MCP JSON-RPC protocol handler."""

import base64
import json

import pytest

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.tools.events import ToolEventBus
from chirp.tools.handler import (
    _parse_meta,
    get_mcp_meta,
    handle_mcp_request,
)
from chirp.tools.registry import ToolRegistry, compile_tools

_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
_META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
_META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"


def _stateless_meta(
    *,
    protocol_version: str = "2026-07-28",
    client_name: str = "test-client",
    client_version: str = "1.0.0",
) -> dict:
    """Build a 2026-07-28 per-request ``_meta`` object."""
    return {
        _META_PROTOCOL_VERSION: protocol_version,
        _META_CLIENT_INFO: {"name": client_name, "version": client_version},
        _META_CLIENT_CAPABILITIES: {},
    }


def _routing_headers(
    *,
    method: str,
    name: str | None = None,
    protocol_version: str = "2026-07-28",
) -> dict[str, str]:
    """Build SEP-2243 Streamable HTTP routing headers."""
    headers = {
        "MCP-Protocol-Version": protocol_version,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def _make_request(
    *,
    method: str = "POST",
    path: str = "/mcp",
    body: dict | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a chirp Request for MCP handler tests."""
    if isinstance(body, dict):
        raw_body = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        raw_body = body
    else:
        raw_body = b""

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    asgi_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
    ]
    if headers:
        for key, value in headers.items():
            asgi_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    return Request.from_asgi(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": asgi_headers,
            "query_string": b"",
        },
        receive,
    )


def _parse_response(response: Response) -> tuple[int, dict]:
    """Extract status and JSON body from a chirp Response."""
    body_bytes = response.body_bytes
    body = json.loads(body_bytes) if body_bytes else {}
    return response.status, body


class TestMCPHandler:
    """Test the MCP JSON-RPC protocol handler at the Request/Response level."""

    def _make_registry(self) -> ToolRegistry:
        async def search(query: str, limit: int = 10) -> list[dict]:
            return [{"name": "item", "query": query, "limit": limit}]

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        return compile_tools(
            [
                ("search", "Search items", search),
                ("greet", "Greet someone", greet),
            ],
            ToolEventBus(),
        )

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        """Legacy initialize is accept-and-noop; advertises current version."""
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["id"] == 1
        assert body["result"]["protocolVersion"] == "2026-07-28"
        assert "capabilities" in body["result"]
        assert "tools" in body["result"]["capabilities"]
        offramp = body["result"]["_meta"]["chirp/legacyOfframp"]
        assert offramp["legacyProtocol"] == "2024-11-05"
        assert offramp["supportedProtocol"] == "2026-07-28"
        assert offramp["removeAfter"] == "2027-07-28"

    @pytest.mark.issue(965)
    @pytest.mark.asyncio
    async def test_stateless_call_with_meta_succeeds(self) -> None:
        """A tools/call with ``_meta`` succeeds with no prior handshake."""
        seen: list = []

        def greet(name: str) -> str:
            seen.append(get_mcp_meta())
            return f"Hello, {name}!"

        registry = compile_tools(
            [("greet", "Greet someone", greet)],
            ToolEventBus(),
        )
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 10,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "World"},
                    "_meta": _stateless_meta(client_name="agent"),
                },
            },
            headers=_routing_headers(method="tools/call", name="greet"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["result"]["content"][0]["text"] == "Hello, World!"
        assert len(seen) == 1
        meta = seen[0]
        assert meta is not None
        assert meta.protocol_version == "2026-07-28"
        assert meta.client_info == {"name": "agent", "version": "1.0.0"}
        assert meta.client_capabilities == {}
        assert get_mcp_meta() is None  # reset after request

    @pytest.mark.issue(965)
    @pytest.mark.asyncio
    async def test_missing_and_legacy_initialize_do_not_error(self) -> None:
        """Missing handshake and legacy initialize must not error."""
        registry = self._make_registry()

        # No initialize — tools/list succeeds (legacy unversioned path warns)
        list_req = _make_request(
            body={"jsonrpc": "2.0", "method": "tools/list", "id": 1, "params": {}},
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            list_resp = await handle_mcp_request(list_req, registry)
        list_status, list_body = _parse_response(list_resp)
        assert list_status == 200
        assert "tools" in list_body["result"]
        assert "error" not in list_body

        # Legacy initialize — accepted, no session created
        init_req = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 2, "params": {}},
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            init_resp = await handle_mcp_request(init_req, registry)
        init_status, init_body = _parse_response(init_resp)
        assert init_status == 200
        assert "error" not in init_body
        assert init_body["result"]["protocolVersion"] == "2026-07-28"

        # notifications/initialized — 204 noop
        note_req = _make_request(
            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            note_resp = await handle_mcp_request(note_req, registry)
        assert note_resp.status == 204

        # Second call with no ordering dependency
        call_req = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 3,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "Stateless"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="greet"),
        )
        call_resp = await handle_mcp_request(call_req, registry)
        call_status, call_body = _parse_response(call_resp)
        assert call_status == 200
        assert call_body["result"]["content"][0]["text"] == "Hello, Stateless!"

    @pytest.mark.issue(965)
    def test_parse_meta_surfaces_fields(self) -> None:
        """``_parse_meta`` extracts reserved identity/version/capability keys."""
        body = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
            "params": {"_meta": _stateless_meta(client_name="inspector")},
        }
        meta = _parse_meta(body)
        assert meta.protocol_version == "2026-07-28"
        assert meta.client_info == {"name": "inspector", "version": "1.0.0"}
        assert meta.client_capabilities == {}
        assert meta.raw[_META_PROTOCOL_VERSION] == "2026-07-28"

        empty = _parse_meta({"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        assert empty.protocol_version is None
        assert empty.raw == {}

    @pytest.mark.asyncio
    async def test_server_discover(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "server/discover",
                "id": "discover-1",
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="server/discover"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        result = body["result"]
        assert result["resultType"] == "complete"
        assert result["supportedVersions"] == ["2026-07-28"]
        assert "tools" in result["capabilities"]
        assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "chirp"

    @pytest.mark.asyncio
    async def test_invalid_meta_type_errors(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 99,
                "params": {"_meta": "not-an-object"},
            },
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["error"]["code"] == -32602
        assert "_meta" in body["error"]["message"]

    @pytest.mark.issue(966)
    @pytest.mark.asyncio
    async def test_routing_headers_agree_with_body(self) -> None:
        """Matching SEP-2243 routing headers pass through to tools/call."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 42,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "Headers"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="greet"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["result"]["content"][0]["text"] == "Hello, Headers!"

    @pytest.mark.issue(966)
    @pytest.mark.asyncio
    async def test_missing_required_routing_header_errors(self) -> None:
        """Modern requests missing a required routing header get HeaderMismatch."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 43,
                "params": {"_meta": _stateless_meta()},
            },
            # Protocol version present → modern path; Mcp-Method omitted.
            headers={"MCP-Protocol-Version": "2026-07-28"},
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["id"] == 43
        assert body["error"]["code"] == -32020
        assert "Mcp-Method" in body["error"]["message"]

    @pytest.mark.issue(966)
    @pytest.mark.asyncio
    async def test_routing_header_method_mismatch_errors(self) -> None:
        """Mcp-Method that disagrees with the JSON-RPC body is HeaderMismatch."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 44,
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/call"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["id"] == 44
        assert body["error"]["code"] == -32020
        assert "Mcp-Method" in body["error"]["message"]
        assert "tools/call" in body["error"]["message"]
        assert "tools/list" in body["error"]["message"]

    @pytest.mark.issue(966)
    @pytest.mark.asyncio
    async def test_routing_header_name_mismatch_errors(self) -> None:
        """Mcp-Name that disagrees with params.name is HeaderMismatch."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 45,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "X"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="search"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32020
        assert "Mcp-Name" in body["error"]["message"]

    @pytest.mark.issue(966)
    @pytest.mark.asyncio
    async def test_routing_header_name_base64_decoded(self) -> None:
        """Base64-sentinel Mcp-Name values are decoded before comparison."""
        registry = self._make_registry()
        encoded = f"=?base64?{base64.b64encode(b'greet').decode('ascii')}?="
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 46,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "B64"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name=encoded),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["result"]["content"][0]["text"] == "Hello, B64!"

    @pytest.mark.asyncio
    async def test_tools_list(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/list"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        tools = body["result"]["tools"]
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"search", "greet"}

    @pytest.mark.asyncio
    async def test_tools_list_schema(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 3,
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/list"),
        )
        response = await handle_mcp_request(request, registry)
        _status, body = _parse_response(response)
        tools = body["result"]["tools"]
        search_tool = next(t for t in tools if t["name"] == "search")
        schema = search_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"] == {"type": "string"}

    @pytest.mark.asyncio
    async def test_tools_call(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 4,
                "params": {
                    "name": "greet",
                    "arguments": {"name": "World"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="greet"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["id"] == 4
        content = body["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_tools_call_async(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 5,
                "params": {
                    "name": "search",
                    "arguments": {"query": "test"},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="search"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        content = body["result"]["content"]
        result = json.loads(content[0]["text"])
        assert result == [{"name": "item", "query": "test", "limit": 10}]

    @pytest.mark.asyncio
    async def test_tools_call_not_found(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 6,
                "params": {
                    "name": "missing",
                    "arguments": {},
                    "_meta": _stateless_meta(),
                },
            },
            headers=_routing_headers(method="tools/call", name="missing"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" in body
        assert body["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_method_not_found(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "unknown/method",
                "id": 7,
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="unknown/method"),
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" in body
        assert body["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        registry = self._make_registry()
        request = _make_request(body=b"not json{{{")
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_empty_body(self) -> None:
        registry = self._make_registry()
        request = _make_request(body=b"")
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_get_method_rejected(self) -> None:
        registry = self._make_registry()
        request = _make_request(method="GET")
        response = await handle_mcp_request(request, registry)
        assert response.status == 405

    @pytest.mark.asyncio
    async def test_missing_rpc_method(self) -> None:
        registry = self._make_registry()
        request = _make_request(body={"jsonrpc": "2.0", "id": 8})
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32600

    @pytest.mark.asyncio
    async def test_notifications_initialized(self) -> None:
        """notifications/initialized has no id — server returns 204."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                # No "id" — this is a JSON-RPC notification
            }
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            response = await handle_mcp_request(request, registry)
        assert response.status == 204

    @pytest.mark.asyncio
    async def test_notification_unknown_method(self) -> None:
        """Any notification (no id) gets 204, even for unknown methods."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "notifications/something_else",
            }
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            response = await handle_mcp_request(request, registry)
        assert response.status == 204


class TestLegacyOfframp967:
    """#967 — documented bridge for handshake-era clients (not a silent break)."""

    def _make_registry(self) -> ToolRegistry:
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        return compile_tools(
            [("greet", "Greet someone", greet)],
            ToolEventBus(),
        )

    @pytest.mark.issue(967)
    def test_is_legacy_detection(self) -> None:
        from chirp.tools.handler import _is_legacy_mcp_request

        legacy_init = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )
        assert _is_legacy_mcp_request(
            legacy_init,
            {"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )

        explicit_legacy = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {
                    "_meta": {_META_PROTOCOL_VERSION: "2024-11-05"},
                },
            },
            headers={"MCP-Protocol-Version": "2024-11-05"},
        )
        assert _is_legacy_mcp_request(
            explicit_legacy,
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {"_meta": {_META_PROTOCOL_VERSION: "2024-11-05"}},
            },
        )

        modern = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {"_meta": _stateless_meta()},
            },
            headers=_routing_headers(method="tools/list"),
        )
        assert not _is_legacy_mcp_request(
            modern,
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {"_meta": _stateless_meta()},
            },
        )

    @pytest.mark.issue(967)
    @pytest.mark.asyncio
    async def test_legacy_initialize_bridged_with_warning_and_meta(self) -> None:
        """Legacy initialize succeeds with DeprecationWarning + offramp _meta."""
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )
        with pytest.warns(DeprecationWarning, match="2027-07-28"):
            response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" not in body
        result = body["result"]
        assert result["protocolVersion"] == "2026-07-28"
        offramp = result["_meta"]["chirp/legacyOfframp"]
        assert offramp["removeAfter"] == "2027-07-28"
        assert "Migrate" in offramp["message"]

    @pytest.mark.issue(967)
    @pytest.mark.asyncio
    async def test_explicit_legacy_version_skips_header_enforcement(self) -> None:
        """Advertising only 2024-11-05 does not trigger HeaderMismatch."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {"_meta": {_META_PROTOCOL_VERSION: "2024-11-05"}},
            },
            headers={"MCP-Protocol-Version": "2024-11-05"},
            # Intentionally omit Mcp-Method — must remain bridged, not -32020.
        )
        with pytest.warns(DeprecationWarning, match="2024-11-05"):
            response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" not in body
        assert "tools" in body["result"]

    @pytest.mark.issue(967)
    @pytest.mark.asyncio
    async def test_modern_path_still_enforces_headers(self) -> None:
        """Modern advertisement without Mcp-Method still returns HeaderMismatch."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {"_meta": _stateless_meta()},
            },
            headers={"MCP-Protocol-Version": "2026-07-28"},
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32020

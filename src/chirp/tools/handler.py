"""MCP JSON-RPC protocol handler.

Handles the Model Context Protocol's Streamable HTTP transport.
Receives a chirp ``Request``, returns a chirp ``Response`` — this means
it participates in the normal middleware pipeline (auth, CORS, rate
limiting all apply).

Implements the minimal MCP surface for the ``2026-07-28`` stateless core:
    - ``server/discover`` — optional capability advertisement
    - ``tools/list`` — return registered tool schemas
    - ``tools/call`` — dispatch to tool handler, return result
    - ``initialize`` / ``notifications/initialized`` — accept-and-noop
      for legacy ``2024-11-05`` clients (no server-side session)

Per-request ``params._meta`` carries protocol version, client identity,
and capabilities. There is no handshake or session state.
"""

from __future__ import annotations

import json as json_module
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, TypedDict

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.tools.registry import ToolRegistry

# Reserved ``_meta`` keys (MCP 2026-07-28 RequestMetaObject)
_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
_META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
_META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
_META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"


class JsonRpcError(TypedDict):
    """JSON-RPC error object (§5.1)."""

    code: int
    message: str


class JsonRpcErrorResponse(TypedDict):
    """JSON-RPC error response envelope."""

    jsonrpc: str
    error: JsonRpcError
    id: str | int | float | None


class JsonRpcSuccessResponse(TypedDict):
    """JSON-RPC success response envelope."""

    jsonrpc: str
    result: Any
    id: str | int | float | None


class McpContentBlock(TypedDict):
    """MCP text content block."""

    type: str
    text: str


@dataclass(frozen=True, slots=True)
class McpRequestMeta:
    """Parsed per-request MCP ``_meta`` (protocol 2026-07-28).

    Missing ``_meta`` (legacy clients) yields empty fields with ``raw={}``.
    """

    protocol_version: str | None
    client_info: dict[str, Any] | None
    client_capabilities: dict[str, Any] | None
    raw: dict[str, Any]


# MCP protocol version
_MCP_VERSION = "2026-07-28"

# Server capabilities (tools only in v1)
_SERVER_INFO = {
    "name": "chirp",
    "version": "0.1.1",
}

_SERVER_CAPABILITIES = {
    "tools": {},
}

_mcp_meta_var: ContextVar[McpRequestMeta | None] = ContextVar(
    "chirp_mcp_request_meta",
    default=None,
)


def get_mcp_meta() -> McpRequestMeta | None:
    """Return parsed ``_meta`` for the current MCP request, or ``None`` outside one."""
    return _mcp_meta_var.get()


def _parse_meta(request_body: dict[str, Any]) -> McpRequestMeta:
    """Extract and normalize ``params._meta`` from a JSON-RPC request body.

    Raises:
        TypeError: When ``_meta`` is present but not a JSON object.
    """
    params = request_body.get("params")
    if not isinstance(params, dict):
        return McpRequestMeta(
            protocol_version=None,
            client_info=None,
            client_capabilities=None,
            raw={},
        )

    meta = params.get("_meta")
    if meta is None:
        return McpRequestMeta(
            protocol_version=None,
            client_info=None,
            client_capabilities=None,
            raw={},
        )
    if not isinstance(meta, dict):
        raise TypeError("_meta must be an object")

    protocol_version = meta.get(_META_PROTOCOL_VERSION)
    if protocol_version is not None and not isinstance(protocol_version, str):
        raise TypeError(f"{_META_PROTOCOL_VERSION!r} must be a string")

    client_info = meta.get(_META_CLIENT_INFO)
    if client_info is not None and not isinstance(client_info, dict):
        raise TypeError(f"{_META_CLIENT_INFO!r} must be an object")

    client_capabilities = meta.get(_META_CLIENT_CAPABILITIES)
    if client_capabilities is not None and not isinstance(client_capabilities, dict):
        raise TypeError(f"{_META_CLIENT_CAPABILITIES!r} must be an object")

    return McpRequestMeta(
        protocol_version=protocol_version,
        client_info=dict(client_info) if client_info is not None else None,
        client_capabilities=(
            dict(client_capabilities) if client_capabilities is not None else None
        ),
        raw=dict(meta),
    )


async def handle_mcp_request(
    request: Request,
    registry: ToolRegistry,
) -> Response:
    """Handle an MCP JSON-RPC request.

    Takes a chirp Request, returns a chirp Response. This function is
    called from within the middleware pipeline in ``handle_request()``,
    so all middleware (auth, CORS, rate limiting) applies.

    Stateless: no handshake or session is required. Legacy ``initialize``
    / ``notifications/initialized`` are accepted as no-ops for back-compat.
    """
    # MCP Streamable HTTP: only POST carries JSON-RPC
    if request.method != "POST":
        return _json_response(
            405,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32600, message="Method not allowed. Use POST."),
                id=None,
            ),
        )

    # Read request body
    body = await request.body()
    if not body:
        return _json_response(
            400,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32700, message="Empty request body"),
                id=None,
            ),
        )

    # Parse JSON-RPC
    try:
        rpc_request = json_module.loads(body)
    except json_module.JSONDecodeError:
        return _json_response(
            400,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32700, message="Parse error"),
                id=None,
            ),
        )

    # Validate JSON-RPC structure
    if not isinstance(rpc_request, dict):
        return _json_response(
            400,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32600, message="Invalid request — expected object"),
                id=None,
            ),
        )

    rpc_method = rpc_request.get("method")
    rpc_id = rpc_request.get("id")
    params = rpc_request.get("params", {})

    # JSON-RPC notifications have no "id" — they expect no response.
    # Legacy MCP's notifications/initialized is the primary example.
    is_notification = "id" not in rpc_request

    if not rpc_method:
        return _json_response(
            400,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32600, message="Missing 'method' field"),
                id=rpc_id,
            ),
        )

    # Handle notifications (no response expected) — accept-and-noop
    if is_notification:
        return _handle_notification(rpc_method)

    try:
        meta = _parse_meta(rpc_request)
    except TypeError as exc:
        return _json_response(
            200,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=JsonRpcError(code=-32602, message=str(exc)),
                id=rpc_id,
            ),
        )

    if not isinstance(params, dict):
        params = {}

    token: Token[McpRequestMeta | None] = _mcp_meta_var.set(meta)
    try:
        result = await _dispatch(rpc_method, params, registry=registry, meta=meta)
    finally:
        _mcp_meta_var.reset(token)

    if isinstance(result, dict) and "error" in result:
        return _json_response(
            200,
            JsonRpcErrorResponse(
                jsonrpc="2.0",
                error=result["error"],
                id=rpc_id,
            ),
        )

    return _json_response(
        200,
        JsonRpcSuccessResponse(
            jsonrpc="2.0",
            result=result,
            id=rpc_id,
        ),
    )


def _handle_notification(method: str) -> Response:
    """Handle a JSON-RPC notification (no response expected).

    Legacy MCP clients send ``notifications/initialized`` after an
    ``initialize`` handshake. Per JSON-RPC, notifications have no ``id``
    and the server MUST NOT reply. We return 204 No Content for all
    notifications (accept-and-noop; no session state).
    """
    _ = method  # acknowledged but not dispatched
    return Response(body="", status=204)


async def _dispatch(
    method: str,
    params: dict[str, Any],
    *,
    registry: ToolRegistry,
    meta: McpRequestMeta,
) -> Any:
    """Route a JSON-RPC method to the appropriate handler."""
    match method:
        case "initialize":
            # Legacy accept-and-noop — no session; advertise current version.
            return _handle_initialize(params)
        case "server/discover":
            return _handle_server_discover(meta)
        case "tools/list":
            return _handle_tools_list(registry)
        case "tools/call":
            return await _handle_tools_call(params, registry)
        case _:
            return {"error": JsonRpcError(code=-32601, message=f"Method not found: {method!r}")}


def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """Legacy ``initialize`` — accept-and-noop capability reply.

    Stateless servers do not require this handshake. Kept for
    ``2024-11-05`` clients; response uses the current protocol version.
    """
    _ = params
    return {
        "protocolVersion": _MCP_VERSION,
        "capabilities": _SERVER_CAPABILITIES,
        "serverInfo": _SERVER_INFO,
    }


def _handle_server_discover(meta: McpRequestMeta) -> dict[str, Any]:
    """Handle MCP ``server/discover`` — optional capability advertisement."""
    _ = meta  # available for future version negotiation / logging
    return {
        "resultType": "complete",
        "supportedVersions": [_MCP_VERSION],
        "capabilities": _SERVER_CAPABILITIES,
        "_meta": {
            _META_SERVER_INFO: dict(_SERVER_INFO),
        },
    }


def _handle_tools_list(registry: ToolRegistry) -> dict[str, Any]:
    """Handle MCP ``tools/list`` — return registered tool schemas."""
    return {"tools": registry.list_tools()}


async def _handle_tools_call(
    params: dict[str, Any],
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Handle MCP ``tools/call`` — dispatch to tool handler."""
    tool_name = params.get("name")
    if not tool_name:
        return {"error": JsonRpcError(code=-32602, message="Missing 'name' in params")}

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return {"error": JsonRpcError(code=-32602, message="'arguments' must be an object")}

    tool = registry.get(tool_name)
    if tool is None:
        return {"error": JsonRpcError(code=-32602, message=f"Tool not found: {tool_name!r}")}

    if tool.approval_required:
        return {
            "error": JsonRpcError(
                code=-32603,
                message=(
                    f"Tool {tool_name!r} requires human approval via the web UI before it can run."
                ),
            )
        }

    try:
        result = await registry.call_tool(tool_name, arguments)
    except KeyError:
        return {"error": JsonRpcError(code=-32602, message=f"Tool not found: {tool_name!r}")}
    except TypeError as exc:
        return {"error": JsonRpcError(code=-32602, message=f"Invalid arguments: {exc}")}
    except Exception as exc:
        return {"error": JsonRpcError(code=-32603, message=f"Tool execution error: {exc}")}

    # MCP tools/call result format: content array
    return {
        "content": [_format_result(result)],
    }


def _format_result(result: Any) -> McpContentBlock:
    """Format a tool result as an MCP content block."""
    if isinstance(result, str):
        return McpContentBlock(type="text", text=result)
    if isinstance(result, dict | list):
        return McpContentBlock(type="text", text=json_module.dumps(result, default=str))
    # Fallback: convert to string
    return McpContentBlock(type="text", text=str(result))


def _json_response(status: int, body: JsonRpcErrorResponse | JsonRpcSuccessResponse) -> Response:
    """Build a chirp Response with JSON content."""
    return Response(
        body=json_module.dumps(body, default=str),
        status=status,
        content_type="application/json; charset=utf-8",
    )

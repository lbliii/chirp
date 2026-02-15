"""MCP JSON-RPC protocol handler.

Handles the Model Context Protocol's Streamable HTTP transport.
Receives a chirp ``Request``, returns a chirp ``Response`` — this means
it participates in the normal middleware pipeline (auth, CORS, rate
limiting all apply).

Implements the minimal MCP surface for v1:
    - ``initialize`` — capability negotiation (tools only)
    - ``notifications/initialized`` — client acknowledgment (no-op)
    - ``tools/list`` — return registered tool schemas
    - ``tools/call`` — dispatch to tool handler, return result
"""

import json as json_module
from typing import Any

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.tools.registry import ToolRegistry

# MCP protocol version
_MCP_VERSION = "2024-11-05"

# Server capabilities (tools only in v1)
_SERVER_INFO = {
    "name": "chirp",
    "version": "0.1.1",
}

_SERVER_CAPABILITIES = {
    "tools": {},
}


async def handle_mcp_request(
    request: Request,
    registry: ToolRegistry,
) -> Response:
    """Handle an MCP JSON-RPC request.

    Takes a chirp Request, returns a chirp Response. This function is
    called from within the middleware pipeline in ``handle_request()``,
    so all middleware (auth, CORS, rate limiting) applies.
    """
    # MCP Streamable HTTP: only POST carries JSON-RPC
    if request.method != "POST":
        return _json_response(405, {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Method not allowed. Use POST."},
            "id": None,
        })

    # Read request body
    body = await request.body()
    if not body:
        return _json_response(400, {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Empty request body"},
            "id": None,
        })

    # Parse JSON-RPC
    try:
        rpc_request = json_module.loads(body)
    except json_module.JSONDecodeError:
        return _json_response(400, {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None,
        })

    # Validate JSON-RPC structure
    if not isinstance(rpc_request, dict):
        return _json_response(400, {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid request — expected object"},
            "id": None,
        })

    rpc_method = rpc_request.get("method")
    rpc_id = rpc_request.get("id")
    params = rpc_request.get("params", {})

    # JSON-RPC notifications have no "id" — they expect no response.
    # MCP's notifications/initialized is the primary example.
    is_notification = "id" not in rpc_request

    if not rpc_method:
        return _json_response(400, {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Missing 'method' field"},
            "id": rpc_id,
        })

    # Handle notifications (no response expected)
    if is_notification:
        return _handle_notification(rpc_method)

    # Dispatch to MCP methods
    result = await _dispatch(rpc_method, params, registry=registry)

    if isinstance(result, dict) and "error" in result:
        return _json_response(200, {
            "jsonrpc": "2.0",
            "error": result["error"],
            "id": rpc_id,
        })

    return _json_response(200, {
        "jsonrpc": "2.0",
        "result": result,
        "id": rpc_id,
    })


def _handle_notification(method: str) -> Response:
    """Handle a JSON-RPC notification (no response expected).

    MCP clients send ``notifications/initialized`` after the initialize
    handshake completes. Per JSON-RPC spec, notifications have no ``id``
    and the server MUST NOT reply. We return 204 No Content.
    """
    # Accept all notifications silently — notifications/initialized
    # is the common case, but future MCP versions may add others.
    _ = method  # acknowledged but not dispatched
    return Response(body="", status=204)


async def _dispatch(
    method: str,
    params: dict[str, Any],
    *,
    registry: ToolRegistry,
) -> Any:
    """Route a JSON-RPC method to the appropriate handler."""
    if method == "initialize":
        return _handle_initialize(params)
    if method == "tools/list":
        return _handle_tools_list(registry)
    if method == "tools/call":
        return await _handle_tools_call(params, registry)

    return {"error": {"code": -32601, "message": f"Method not found: {method!r}"}}


def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP ``initialize`` — capability negotiation."""
    return {
        "protocolVersion": _MCP_VERSION,
        "capabilities": _SERVER_CAPABILITIES,
        "serverInfo": _SERVER_INFO,
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
        return {"error": {"code": -32602, "message": "Missing 'name' in params"}}

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return {"error": {"code": -32602, "message": "'arguments' must be an object"}}

    try:
        result = await registry.call_tool(tool_name, arguments)
    except KeyError:
        return {"error": {"code": -32602, "message": f"Tool not found: {tool_name!r}"}}
    except TypeError as exc:
        return {"error": {"code": -32602, "message": f"Invalid arguments: {exc}"}}
    except Exception as exc:
        return {"error": {"code": -32603, "message": f"Tool execution error: {exc}"}}

    # MCP tools/call result format: content array
    return {
        "content": [_format_result(result)],
    }


def _format_result(result: Any) -> dict[str, Any]:
    """Format a tool result as an MCP content block."""
    if isinstance(result, str):
        return {"type": "text", "text": result}
    if isinstance(result, dict | list):
        return {"type": "text", "text": json_module.dumps(result, default=str)}
    # Fallback: convert to string
    return {"type": "text", "text": str(result)}


def _json_response(status: int, body: dict[str, Any]) -> Response:
    """Build a chirp Response with JSON content."""
    return Response(
        body=json_module.dumps(body, default=str),
        status=status,
        content_type="application/json; charset=utf-8",
    )

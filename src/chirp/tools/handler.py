"""MCP JSON-RPC protocol handler over ASGI.

Handles the Model Context Protocol's Streamable HTTP transport at a
dedicated path (default: ``/mcp``). Receives JSON-RPC POST requests,
dispatches to the tool registry, and sends JSON-RPC responses.

Implements the minimal MCP surface for v1:
    - ``initialize`` — capability negotiation (tools only)
    - ``tools/list`` — return registered tool schemas
    - ``tools/call`` — dispatch to tool handler, return result

This is a dedicated ASGI handler (like ``realtime/sse.py``), not a
regular chirp route. It receives raw ASGI scope/receive/send and
handles JSON-RPC framing itself.
"""

import json as json_module
from typing import Any

from chirp._internal.asgi import Receive, Scope, Send
from chirp.tools.registry import ToolRegistry

# MCP protocol version
_MCP_VERSION = "2024-11-05"

# Server capabilities (tools only in v1)
_SERVER_INFO = {
    "name": "chirp",
    "version": "0.1.0",
}

_SERVER_CAPABILITIES = {
    "tools": {},
}


async def handle_mcp(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    registry: ToolRegistry,
) -> None:
    """Handle an MCP JSON-RPC request over HTTP.

    Reads the full request body, parses the JSON-RPC envelope, dispatches
    to the appropriate method, and sends a JSON-RPC response.
    """
    method = scope.get("method", "GET")

    # MCP Streamable HTTP: only POST carries JSON-RPC
    if method != "POST":
        await _send_json(send, status=405, body={
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Method not allowed. Use POST."},
            "id": None,
        })
        return

    # Read request body
    body = await _read_body(receive)
    if not body:
        await _send_json(send, status=400, body={
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Empty request body"},
            "id": None,
        })
        return

    # Parse JSON-RPC
    try:
        request = json_module.loads(body)
    except json_module.JSONDecodeError:
        await _send_json(send, status=400, body={
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None,
        })
        return

    # Validate JSON-RPC structure
    if not isinstance(request, dict):
        await _send_json(send, status=400, body={
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid request — expected object"},
            "id": None,
        })
        return

    rpc_method = request.get("method")
    rpc_id = request.get("id")
    params = request.get("params", {})

    if not rpc_method:
        await _send_json(send, status=400, body={
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Missing 'method' field"},
            "id": rpc_id,
        })
        return

    # Dispatch to MCP methods
    result = await _dispatch(rpc_method, params, registry=registry)

    if isinstance(result, dict) and "error" in result:
        # Error response
        await _send_json(send, status=200, body={
            "jsonrpc": "2.0",
            "error": result["error"],
            "id": rpc_id,
        })
    else:
        # Success response
        await _send_json(send, status=200, body={
            "jsonrpc": "2.0",
            "result": result,
            "id": rpc_id,
        })


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


# -- ASGI helpers --


async def _read_body(receive: Receive) -> bytes:
    """Read the full request body from ASGI receive."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        body = message.get("body", b"")
        if body:
            chunks.append(body)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _send_json(
    send: Send,
    *,
    status: int,
    body: dict[str, Any],
) -> None:
    """Send a JSON response over ASGI."""
    payload = json_module.dumps(body, default=str).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("latin-1")),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": payload,
    })

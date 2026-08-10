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

Streamable HTTP routing headers (SEP-2243) are validated when a modern
protocol version is advertised via ``MCP-Protocol-Version`` or
``params._meta`` — see ``_validate_routing_headers``.

Legacy ``2024-11-05`` clients are **bridged** (not hard-errored) through a
12-month offramp ending ``2027-07-28`` (MCP feature-lifecycle minimum).
Detection emits ``DeprecationWarning`` and documents the window in
``initialize`` result ``_meta``; ``app.check()`` surfaces an INFO
``mcp_legacy`` issue when tools are registered.
"""

from __future__ import annotations

import base64
import json as json_module
import re
import warnings
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
_META_LEGACY_OFFRAMP = "chirp/legacyOfframp"

# SEP-2243 / Streamable HTTP 2026-07-28
_HEADER_PROTOCOL_VERSION = "MCP-Protocol-Version"
_HEADER_METHOD = "Mcp-Method"
_HEADER_NAME = "Mcp-Name"
_HEADER_MISMATCH_CODE = -32020
_METHODS_REQUIRING_NAME = frozenset({"tools/call", "resources/read", "prompts/get"})
_BASE64_SENTINEL = re.compile(r"^=\?base64\?(?P<data>.+)\?=$")

# Legacy handshake-era protocol (pre-stateless). Bridged until offramp date.
_LEGACY_PROTOCOL_VERSION = "2024-11-05"
# 12 months after 2026-07-28 per MCP feature-lifecycle deprecation policy.
_LEGACY_OFFRAMP_UNTIL = "2027-07-28"
_LEGACY_HANDSHAKE_METHODS = frozenset({"initialize", "notifications/initialized"})


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

# Protocol versions this server negotiates on ``initialize`` (newest first).
# A client that requests one of these gets it echoed back; anything else
# (including an omitted version) falls back to ``_MCP_VERSION``.
_SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    _MCP_VERSION,
    "2025-06-18",
    "2025-03-26",
    _LEGACY_PROTOCOL_VERSION,
)
_NEGOTIABLE_PROTOCOL_VERSIONS = frozenset(_SUPPORTED_PROTOCOL_VERSIONS)

# Versions that carry SEP-2243 Streamable HTTP routing headers
# (``MCP-Protocol-Version`` / ``Mcp-Method`` / ``Mcp-Name``).  Standard MCP
# 2025-06-18 clients use plain JSON-RPC bodies and MUST NOT be required to
# supply routing headers; dispatch reads the method/name from the body.
_ROUTING_HEADER_PROTOCOL_VERSIONS = frozenset({_MCP_VERSION})

# Server capabilities (tools only in v1)
_SERVER_INFO = {
    "name": "chirp",
    "version": "0.1.1",
}

_SERVER_CAPABILITIES = {
    "tools": {},
}

_LEGACY_DEPRECATION_MESSAGE = (
    f"MCP protocol {_LEGACY_PROTOCOL_VERSION} (handshake-era) clients are deprecated. "
    f"Migrate to {_MCP_VERSION} with per-request params._meta and SEP-2243 routing "
    f"headers (MCP-Protocol-Version, Mcp-Method, Mcp-Name). "
    f"Legacy bridge remains until {_LEGACY_OFFRAMP_UNTIL}."
)

_mcp_meta_var: ContextVar[McpRequestMeta | None] = ContextVar(
    "chirp_mcp_request_meta",
    default=None,
)


def get_mcp_meta() -> McpRequestMeta | None:
    """Return parsed ``_meta`` for the current MCP request, or ``None`` outside one."""
    return _mcp_meta_var.get()


def _header_value(request: Request, name: str) -> str | None:
    """Return a trimmed HTTP header value, or ``None`` if absent/blank."""
    raw = request.headers.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value if value else None


def _decode_mcp_header_value(value: str) -> str | None:
    """Decode a plain or Base64-sentinel MCP header value.

    Returns ``None`` when a Base64 sentinel is present but malformed
    (invalid padding/characters) — callers treat that as HeaderMismatch.
    """
    match = _BASE64_SENTINEL.fullmatch(value)
    if match is None:
        return value
    try:
        return base64.b64decode(match.group("data"), validate=True).decode("utf-8")
    except ValueError, UnicodeDecodeError:
        return None


def _body_protocol_version(request_body: dict[str, Any]) -> str | None:
    """Return ``params._meta`` protocol version when present and a string."""
    params = request_body.get("params")
    if not isinstance(params, dict):
        return None
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None
    version = meta.get(_META_PROTOCOL_VERSION)
    return version if isinstance(version, str) else None


def _requested_version_from_params(params: dict[str, Any]) -> str | None:
    """Return the client's requested protocol version from ``initialize`` params.

    Prefers the standard MCP ``params.protocolVersion`` field, then Chirp's
    per-request ``params._meta`` protocol version.
    """
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested:
        return requested
    meta = params.get("_meta")
    if isinstance(meta, dict):
        version = meta.get(_META_PROTOCOL_VERSION)
        if isinstance(version, str) and version:
            return version
    return None


def _initialize_request_version(request_body: dict[str, Any]) -> str | None:
    """Return the ``initialize`` requested protocol version from a request body."""
    params = request_body.get("params")
    if not isinstance(params, dict):
        return None
    return _requested_version_from_params(params)


def _advertised_protocol_versions(
    request: Request,
    request_body: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Return ``(header_version, body_version)`` advertisements, if any."""
    return (
        _header_value(request, _HEADER_PROTOCOL_VERSION),
        _body_protocol_version(request_body),
    )


def _has_modern_protocol_advertisement(
    header_version: str | None,
    body_version: str | None,
) -> bool:
    """Return whether any non-legacy protocol version is advertised."""
    for version in (header_version, body_version):
        if version is not None and version != _LEGACY_PROTOCOL_VERSION:
            return True
    return False


def _requires_routing_headers(header_version: str | None, body_version: str | None) -> bool:
    """Return whether an advertised version mandates SEP-2243 routing headers.

    Only versions in ``_ROUTING_HEADER_PROTOCOL_VERSIONS`` (2026-07-28+) define
    ``Mcp-Method`` / ``Mcp-Name`` routing headers.  Standard 2025-06-18 clients
    carry method/name in the JSON-RPC body and are not held to that contract.
    """
    return any(
        version in _ROUTING_HEADER_PROTOCOL_VERSIONS
        for version in (header_version, body_version)
        if version is not None
    )


def _is_legacy_mcp_request(request: Request, request_body: dict[str, Any]) -> bool:
    """Detect handshake-era / unversioned MCP clients on the legacy offramp.

    A request is legacy when:

    - it advertises ``2024-11-05`` via header or ``params._meta``, or
    - it is a handshake method (``initialize`` /
      ``notifications/initialized``) that does not carry a known non-legacy
      protocol version, or
    - it advertises no protocol version at all (SEP-2243 not enforced).

    Standard ``2025-06-18`` and modern ``2026-07-28`` advertisements — including
    an ``initialize`` that carries ``params.protocolVersion`` — are not legacy.
    """
    header_version, body_version = _advertised_protocol_versions(request, request_body)
    if header_version == _LEGACY_PROTOCOL_VERSION or body_version == _LEGACY_PROTOCOL_VERSION:
        return True
    if _has_modern_protocol_advertisement(header_version, body_version):
        return False
    method = request_body.get("method")
    if isinstance(method, str) and method in _LEGACY_HANDSHAKE_METHODS:
        # A standard ``initialize`` advertises its version via
        # ``params.protocolVersion`` rather than a header/_meta field.  A known
        # non-legacy request is modern; anything else stays on the offramp.
        requested = _initialize_request_version(request_body)
        return requested is None or requested == _LEGACY_PROTOCOL_VERSION
    return header_version is None and body_version is None


def _emit_legacy_deprecation_warning() -> None:
    """Emit the documented legacy-client ``DeprecationWarning`` (bridge path)."""
    warnings.warn(_LEGACY_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)


def _legacy_offramp_meta() -> dict[str, Any]:
    """Structured deprecation note for legacy ``initialize`` responses."""
    return {
        "legacyProtocol": _LEGACY_PROTOCOL_VERSION,
        "supportedProtocol": _MCP_VERSION,
        "removeAfter": _LEGACY_OFFRAMP_UNTIL,
        "message": _LEGACY_DEPRECATION_MESSAGE,
    }


def _body_name(request_body: dict[str, Any]) -> str | None:
    """Return ``params.name`` or ``params.uri`` for name-bearing RPCs."""
    params = request_body.get("params")
    if not isinstance(params, dict):
        return None
    name = params.get("name")
    if isinstance(name, str):
        return name
    uri = params.get("uri")
    return uri if isinstance(uri, str) else None


def _header_mismatch_response(
    rpc_id: str | int | float | None,
    message: str,
) -> Response:
    """Build the SEP-2243 ``HeaderMismatch`` (-32020) JSON-RPC error."""
    return _json_response(
        400,
        JsonRpcErrorResponse(
            jsonrpc="2.0",
            error=JsonRpcError(code=_HEADER_MISMATCH_CODE, message=message),
            id=rpc_id,
        ),
    )


def _validate_routing_headers(
    request: Request,
    request_body: dict[str, Any],
    *,
    rpc_id: str | int | float | None,
) -> Response | None:
    """Validate Streamable HTTP routing headers against the JSON-RPC body.

    Enforcement is gated on a **SEP-2243** protocol advertisement
    (``_ROUTING_HEADER_PROTOCOL_VERSIONS``; 2026-07-28+) via
    ``MCP-Protocol-Version`` and/or ``params._meta``. Standard 2025-06-18
    clients carry method/name in the JSON-RPC body and are skipped, as are
    legacy ``2024-11-05`` and unversioned requests (bridged until
    ``2027-07-28``). When required, missing/mismatched headers return HTTP 400
    with JSON-RPC ``HeaderMismatch`` (``-32020``).

    Returns:
        An error ``Response`` on failure, or ``None`` when validation passes
        or is skipped.
    """
    header_version, body_version = _advertised_protocol_versions(request, request_body)
    if not _requires_routing_headers(header_version, body_version):
        return None

    if header_version is None:
        return _header_mismatch_response(
            rpc_id,
            f"Missing required header: {_HEADER_PROTOCOL_VERSION}",
        )

    header_method = _header_value(request, _HEADER_METHOD)
    if header_method is None:
        return _header_mismatch_response(
            rpc_id,
            f"Missing required header: {_HEADER_METHOD}",
        )

    body_method = request_body.get("method")
    if not isinstance(body_method, str) or header_method != body_method:
        return _header_mismatch_response(
            rpc_id,
            (
                f"Header mismatch: {_HEADER_METHOD} header value "
                f"{header_method!r} does not match body value {body_method!r}"
            ),
        )

    if body_version is None or header_version != body_version:
        return _header_mismatch_response(
            rpc_id,
            (
                f"Header mismatch: {_HEADER_PROTOCOL_VERSION} header value "
                f"{header_version!r} does not match body value {body_version!r}"
            ),
        )

    if body_method in _METHODS_REQUIRING_NAME:
        header_name_raw = _header_value(request, _HEADER_NAME)
        if header_name_raw is None:
            return _header_mismatch_response(
                rpc_id,
                f"Missing required header: {_HEADER_NAME}",
            )
        header_name = _decode_mcp_header_value(header_name_raw)
        body_name = _body_name(request_body)
        if header_name is None or header_name != body_name:
            display = header_name_raw if header_name is None else header_name
            return _header_mismatch_response(
                rpc_id,
                (
                    f"Header mismatch: {_HEADER_NAME} header value "
                    f"{display!r} does not match body value {body_name!r}"
                ),
            )

    return None


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

    # Legacy offramp: bridge (warn), do not hard-error during the window.
    if _is_legacy_mcp_request(request, rpc_request):
        _emit_legacy_deprecation_warning()

    # SEP-2243 routing headers — validate before dispatch / notification noop.
    header_error = _validate_routing_headers(request, rpc_request, rpc_id=rpc_id)
    if header_error is not None:
        return header_error

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
            # Accept-and-noop (no session); negotiate the protocol version.
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
    """MCP ``initialize`` — accept-and-noop capability reply with negotiation.

    Stateless servers need no handshake, but standard clients negotiate a
    protocol version here.  When the client requests a version this server
    supports (``_NEGOTIABLE_PROTOCOL_VERSIONS``) the response echoes it;
    otherwise it advertises the current version (``_MCP_VERSION``).

    Handshake-era clients — those that request no version, or the legacy
    ``2024-11-05`` — also receive the structured deprecation offramp note in
    ``_meta`` (bridged until ``_LEGACY_OFFRAMP_UNTIL``).
    """
    requested = _requested_version_from_params(params)
    negotiated = requested if requested in _NEGOTIABLE_PROTOCOL_VERSIONS else _MCP_VERSION

    meta: dict[str, Any] = {_META_SERVER_INFO: dict(_SERVER_INFO)}
    if requested is None or negotiated == _LEGACY_PROTOCOL_VERSION:
        meta[_META_LEGACY_OFFRAMP] = _legacy_offramp_meta()

    return {
        "protocolVersion": negotiated,
        "capabilities": _SERVER_CAPABILITIES,
        "serverInfo": _SERVER_INFO,
        "_meta": meta,
    }


def _handle_server_discover(meta: McpRequestMeta) -> dict[str, Any]:
    """Handle MCP ``server/discover`` — optional capability advertisement."""
    _ = meta  # available for future version negotiation / logging
    return {
        "resultType": "complete",
        "supportedVersions": list(_SUPPORTED_PROTOCOL_VERSIONS),
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

    from chirp.errors import HTTPError, ToolAuthError

    try:
        result = await registry.call_tool(tool_name, arguments)
    except KeyError:
        return {"error": JsonRpcError(code=-32602, message=f"Tool not found: {tool_name!r}")}
    except TypeError as exc:
        return {"error": JsonRpcError(code=-32602, message=f"Invalid arguments: {exc}")}
    except ToolAuthError as exc:
        # skill.tool scopes (and similar) map enforce_auth 401/403 here.
        message = exc.detail or ("Forbidden" if exc.status == 403 else "Unauthorized")
        return {"error": JsonRpcError(code=-32603, message=message)}
    except HTTPError as exc:
        # Defensive: a tool that raises HTTPError directly (frozen) may still
        # surface here if dispatch did not rewrite it.
        if exc.status in (401, 403):
            message = exc.detail or ("Forbidden" if exc.status == 403 else "Unauthorized")
            return {"error": JsonRpcError(code=-32603, message=message)}
        return {"error": JsonRpcError(code=-32603, message=f"Tool execution error: {exc}")}
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

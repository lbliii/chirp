"""Regression coverage for schema validation before MCP tool dispatch (#1030)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from chirp.tools.events import ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import ToolDef, ToolRegistry, compile_tools
from tests.test_tools.test_mcp_handler import _make_request, _parse_response

pytestmark = [pytest.mark.issue(1030), pytest.mark.asyncio]


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.parametrize(
    ("arguments", "detail"),
    [
        ({"values": "private input"}, "['values']: expected array"),
        ({}, "['values']: required argument is missing"),
        ({"values": [1, "private input"]}, "['values'][1]: expected integer"),
        ({"values": [True]}, "['values'][0]: expected integer"),
        ({"values": [1.5]}, "['values'][0]: expected integer"),
        ({"values": None}, "['values']: expected array"),
    ],
)
async def test_invalid_arguments_never_enter_handler(arguments, detail, is_async) -> None:
    entered = []

    def sync_handler(values: list[int]) -> int:
        entered.append(values)
        raise ValueError("opaque domain failure")

    async def async_handler(values: list[int]) -> int:
        return sync_handler(values)

    bus = AsyncMock(spec=ToolEventBus)
    registry = compile_tools(
        [("total", "Sum values", async_handler if is_async else sync_handler)], bus
    )
    request = _make_request(
        body={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": "validation-1030",
            "params": {"name": "total", "arguments": arguments},
        },
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    response = await handle_mcp_request(request, registry)
    status, body = _parse_response(response)
    assert status == 200
    assert body == {
        "jsonrpc": "2.0",
        "id": "validation-1030",
        "error": {"code": -32602, "message": f"Invalid arguments: Tool 'total' arguments{detail}"},
    }
    assert entered == []
    bus.emit.assert_not_awaited()


@pytest.mark.parametrize(
    ("annotation", "invalid", "valid"),
    [(str, 42, "ok"), (float, True, 2), (bool, 1, False), (dict[str, Any], [], {})],
)
async def test_advertised_scalar_and_object_types(annotation, invalid, valid) -> None:
    def echo(value):
        return value

    echo.__annotations__["value"] = annotation
    registry = compile_tools([("echo", "Echo", echo)], ToolEventBus())
    with pytest.raises(TypeError, match="Tool 'echo' arguments"):
        await registry.call_tool("echo", {"value": invalid})
    assert await registry.call_tool("echo", {"value": valid}) == valid


@pytest.mark.parametrize("is_async", [False, True])
async def test_valid_call_preserves_values_defaults_schema_and_event(is_async) -> None:
    def sync_handler(values: list[int], label: str | None = None) -> dict:
        return {"values": values, "label": label}

    async def async_handler(values: list[int], label: str | None = None) -> dict:
        return sync_handler(values, label)

    bus = AsyncMock(spec=ToolEventBus)
    registry = compile_tools(
        [("total", "Sum values", async_handler if is_async else sync_handler)], bus
    )
    schema = {
        "type": "object",
        "properties": {
            "values": {"type": "array", "items": {"type": "integer"}},
            "label": {"type": "string"},
        },
        "required": ["values"],
    }
    assert registry.list_tools()[0]["inputSchema"] == schema
    arguments = {"values": [1, 2.0]}
    request = _make_request(
        body={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1030,
            "params": {"name": "total", "arguments": arguments},
        },
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    status, body = _parse_response(await handle_mcp_request(request, registry))
    assert status == 200
    assert body["result"]["content"][0]["text"] == '{"values": [1, 2.0], "label": null}'
    event = bus.emit.await_args.args[0]
    assert event.arguments == arguments
    assert isinstance(event.result["values"][1], float)
    assert registry.list_tools()[0]["inputSchema"] == schema


async def test_schema_does_not_restrict_unadvertised_kwargs() -> None:
    def echo(**kwargs):
        return kwargs

    registry = ToolRegistry(
        [ToolDef("echo", "Echo", echo, {"type": "object", "properties": {}})], ToolEventBus()
    )
    assert await registry.call_tool("echo", {"extra": [1]}) == {"extra": [1]}


async def test_unresolved_annotation_fails_at_registration_with_remedy() -> None:
    def echo(value):
        return value

    echo.__annotations__["value"] = "MissingToolArgumentType"
    with pytest.raises(ValueError, match=r"inputSchema.*echo.*module globals"):
        compile_tools([("echo", "Echo", echo)], ToolEventBus())


@pytest.mark.parametrize("value", ["recipient", ["recipient"], []])
async def test_postponed_union_accepts_each_advertised_variant(value) -> None:
    def echo(recipients: list[str] | str):
        return recipients

    registry = compile_tools([("echo", "Echo", echo)], ToolEventBus())
    assert registry.list_tools()[0]["inputSchema"]["properties"]["recipients"] == {
        "anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]
    }
    assert await registry.call_tool("echo", {"recipients": value}) == value


@pytest.mark.parametrize("value", [42, [42], None])
async def test_postponed_union_rejects_invalid_values_before_handler(value) -> None:
    entered = []

    def echo(recipients: list[str] | str):
        entered.append(recipients)
        return recipients

    registry = compile_tools([("echo", "Echo", echo)], ToolEventBus())
    request = _make_request(
        body={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1030,
            "params": {"name": "echo", "arguments": {"recipients": value}},
        },
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    _, body = _parse_response(await handle_mcp_request(request, registry))
    assert body["error"]["code"] == -32602
    assert "Tool 'echo' arguments['recipients']" in body["error"]["message"]
    assert "expected string" in body["error"]["message"]
    assert entered == []


async def test_optional_union_keeps_non_null_variants_and_omission_default() -> None:
    def echo(value: list[str] | str | None = None):
        return value

    registry = compile_tools([("echo", "Echo", echo)], ToolEventBus())
    assert await registry.call_tool("echo", {}) is None
    assert await registry.call_tool("echo", {"value": ["recipient"]}) == ["recipient"]
    assert await registry.call_tool("echo", {"value": "recipient"}) == "recipient"
    with pytest.raises(TypeError, match="No matching argument schema"):
        await registry.call_tool("echo", {"value": None})

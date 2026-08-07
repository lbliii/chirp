"""Tests for tool approval store and registry gates."""

from __future__ import annotations

import json

import pytest

from chirp.tools.approval import (
    InMemoryToolApprovalStore,
    ToolApprovalError,
)
from chirp.tools.events import ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import ToolDef, ToolRegistry


@pytest.mark.issue(442)
class TestToolRegistryApproval:
    async def test_approval_required_raises_without_grant(self) -> None:
        bus = ToolEventBus()

        def delete_all() -> int:
            return 3

        registry = ToolRegistry(
            [
                ToolDef(
                    name="delete_all",
                    description="Delete everything",
                    handler=delete_all,
                    schema={"type": "object", "properties": {}},
                    approval_required=True,
                )
            ],
            bus,
        )
        with pytest.raises(ToolApprovalError):
            await registry.call_tool("delete_all", {})

    async def test_approval_granted_executes_tool(self) -> None:
        bus = ToolEventBus()
        seen: list[str] = []

        def delete_all() -> int:
            seen.append("ran")
            return 1

        registry = ToolRegistry(
            [
                ToolDef(
                    name="delete_all",
                    description="Delete everything",
                    handler=delete_all,
                    schema={"type": "object", "properties": {}},
                    approval_required=True,
                )
            ],
            bus,
        )
        result = await registry.call_tool("delete_all", {}, approval_granted=True)
        assert result == 1
        assert seen == ["ran"]


@pytest.mark.issue(442)
class TestInMemoryToolApprovalStore:
    @pytest.mark.asyncio
    async def test_create_approve_consume(self) -> None:
        store = InMemoryToolApprovalStore()
        pending = await store.create(
            thread_id="t1",
            call_id="c1",
            tool_name="delete_all",
            arguments={"force": True},
        )
        assert pending.status == "pending"
        approved = await store.mark_approved(pending.approval_id)
        assert approved.status == "approved"
        consumed = await store.consume(pending.approval_id)
        assert consumed is not None
        assert consumed.status == "approved"
        assert await store.get(pending.approval_id) is None

    @pytest.mark.asyncio
    async def test_consume_pending_returns_none(self) -> None:
        store = InMemoryToolApprovalStore()
        pending = await store.create(
            thread_id="t1",
            call_id="c1",
            tool_name="delete_all",
            arguments={},
        )
        assert await store.consume(pending.approval_id) is None


@pytest.mark.issue(442)
class TestMcpApprovalRequired:
    @pytest.mark.asyncio
    async def test_mcp_call_rejects_approval_required_tool(self) -> None:
        bus = ToolEventBus()

        def delete_all() -> int:
            return 0

        registry = ToolRegistry(
            [
                ToolDef(
                    name="delete_all",
                    description="Delete everything",
                    handler=delete_all,
                    schema={"type": "object", "properties": {}},
                    approval_required=True,
                )
            ],
            bus,
        )

        class _Req:
            method = "POST"

            @property
            def headers(self) -> dict[str, str]:
                return {
                    "MCP-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "tools/call",
                    "Mcp-Name": "delete_all",
                }

            async def body(self) -> bytes:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": 1,
                    "params": {
                        "name": "delete_all",
                        "arguments": {},
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            "io.modelcontextprotocol/clientCapabilities": {},
                        },
                    },
                }
                return json.dumps(payload).encode()

        response = await handle_mcp_request(_Req(), registry)
        body = json.loads(response.body)
        assert "error" in body
        assert "human approval" in body["error"]["message"].lower()

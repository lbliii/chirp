"""Proof for #983 — ToolEventBus → EventStream live invocation log."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kida import DictLoader

from chirp import App, AppConfig
from chirp.skill import (
    DEFAULT_INVOCATION_LOG_PATH,
    Skill,
    mount_skills,
)
from chirp.testing import TestClient
from chirp.tools import (
    DEFAULT_INVOCATION_LOG_TEMPLATE,
    mount_invocation_log,
    tool_event_stream,
)
from chirp.tools.events import ToolCallEvent, ToolEventBus

_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _make_skill(name: str, tool_name: str) -> Skill:
    private, public = _keypair()
    skill = Skill(
        name,
        version="1.0.0",
        private_key=private,
        key_id=f"{name}-key",
        public_key=public,
    )

    @skill.tool(tool_name, description=f"{name}.{tool_name}")
    def handler(value: str) -> dict[str, str]:
        return {"skill": name, "tool": tool_name, "value": value}

    return skill


def _modern_mcp_params(**extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "_meta": {
            _META_PROTOCOL_VERSION: "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    params.update(extra)
    return params


def _modern_mcp_headers(method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "mcp-protocol-version": "2026-07-28",
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    return headers


@pytest.mark.issue(983)
class TestLiveInvocationLogIssue983:
    def test_tool_event_stream_yields_fragment_for_emitted_event(self) -> None:
        bus = ToolEventBus()
        stream = tool_event_stream(
            bus,
            template="log.html",
            block="row",
        )

        async def _probe() -> None:
            seen: list[Any] = []

            async def collect() -> None:
                async for item in stream.generator:
                    seen.append(item)
                    break

            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.05)
            event = ToolCallEvent(
                tool_name="ping",
                arguments={"x": 1},
                result={"ok": True},
                timestamp=1.0,
                call_id="abc123def456",
            )
            await bus.emit(event)
            await asyncio.wait_for(collector, timeout=1.0)

            assert len(seen) == 1
            frag = seen[0]
            assert frag.template_name == "log.html"
            assert frag.block_name == "row"
            assert frag.context["event"] is event

        asyncio.run(_probe())

    def test_mount_invocation_log_streams_tool_call_over_sse(self) -> None:
        app = App(
            config=AppConfig(
                extra_loaders=(
                    DictLoader(
                        {
                            "page.html": "<html><body>ok</body></html>",
                        }
                    ),
                ),
            )
        )

        @app.tool("greet", description="Greet someone")
        def greet(name: str) -> dict[str, str]:
            return {"hello": name}

        @app.route("/")
        def index() -> str:
            return "ok"

        path = mount_invocation_log(app)
        assert path == DEFAULT_INVOCATION_LOG_PATH

        async def _probe() -> None:
            async with TestClient(app) as client:

                async def call_tool_after_delay() -> None:
                    await asyncio.sleep(0.1)
                    await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": 1,
                            "params": _modern_mcp_params(
                                name="greet",
                                arguments={"name": "orrery"},
                            ),
                        },
                        headers=_modern_mcp_headers("tools/call", "greet"),
                    )
                    await asyncio.sleep(0.15)

                task = asyncio.create_task(call_tool_after_delay())
                result = await client.sse(path, max_events=1, timeout=2.0)
                await task

                assert result.status == 200
                assert result.headers.get("content-type") == "text/event-stream"
                assert result.events, "expected an invocation_row event after the tool call"
                event = result.events[0]
                assert (event.event or "message") == "message"
                assert "greet" in event.data
                assert 'class="tool-name"' in event.data
                assert "orrery" in event.data

        asyncio.run(_probe())

    def test_mount_skills_wires_invocation_log_by_default(self) -> None:
        skill = _make_skill("alpha", "echo_alpha")
        app = App(
            config=AppConfig(
                extra_loaders=(DictLoader({"page.html": "<html><body>ok</body></html>"}),),
            )
        )

        @app.route("/")
        def index() -> str:
            return "ok"

        registry = mount_skills(app, (skill,))
        assert registry.invocation_log_path == DEFAULT_INVOCATION_LOG_PATH

        async def _probe() -> None:
            async with TestClient(app) as client:

                async def call_tool_after_delay() -> None:
                    await asyncio.sleep(0.1)
                    await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": 2,
                            "params": _modern_mcp_params(
                                name="echo_alpha",
                                arguments={"value": "live-log"},
                            ),
                        },
                        headers=_modern_mcp_headers("tools/call", "echo_alpha"),
                    )
                    await asyncio.sleep(0.15)

                task = asyncio.create_task(call_tool_after_delay())
                result = await client.sse(
                    DEFAULT_INVOCATION_LOG_PATH,
                    max_events=1,
                    timeout=2.0,
                )
                await task

                assert result.status == 200
                assert result.events
                data = result.events[0].data
                assert "echo_alpha" in data
                assert "live-log" in data
                assert DEFAULT_INVOCATION_LOG_TEMPLATE  # packaged template name in use

        asyncio.run(_probe())

    def test_mount_skills_can_disable_invocation_log(self) -> None:
        skill = _make_skill("solo", "ping")
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        registry = mount_skills(app, (skill,), invocation_log_path=None)
        assert registry.invocation_log_path is None
        app.freeze()

        async def _probe() -> None:
            async with TestClient(app) as client:
                response = await client.get(DEFAULT_INVOCATION_LOG_PATH)
                assert response.status == 404

        asyncio.run(_probe())

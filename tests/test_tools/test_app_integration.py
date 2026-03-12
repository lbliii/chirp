"""Tests for chirp App tool integration — decorator, registry, MCP endpoint."""

import asyncio
import json
from typing import Any

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.tools.events import ToolEventBus


def _make_asgi_harness() -> tuple[
    Any,  # receive
    Any,  # send
    dict,  # result container {status, body}
]:
    """Build ASGI receive/send for app integration tests."""
    result: dict[str, Any] = {"status": 0, "body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    return receive, send, result


class TestAppToolIntegration:
    def test_tool_decorator(self) -> None:
        app = App()

        @app.tool("search", description="Search things")
        async def search(query: str) -> list[dict]:
            return []

        assert len(app._pending_tools) == 1
        assert app._pending_tools[0].name == "search"
        assert app._pending_tools[0].description == "Search things"

    def test_tool_events_property(self) -> None:
        app = App()
        assert isinstance(app.tool_events, ToolEventBus)

    def test_tool_compiled_at_freeze(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        @app.tool("search", description="Search")
        async def search(query: str) -> list[dict]:
            return []

        app._ensure_frozen()
        assert app._tool_registry is not None
        assert len(app._tool_registry) == 1
        assert "search" in app._tool_registry

    def test_cannot_register_tool_after_freeze(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.tool("search", description="Search")
            async def search(query: str) -> list[dict]:
                return []

    @pytest.mark.asyncio
    async def test_mcp_endpoint(self) -> None:
        """Full integration: POST JSON-RPC to /mcp via ASGI."""
        app = App()

        @app.route("/")
        def index():
            return "hello"

        @app.tool("echo", description="Echo input")
        def echo(message: str) -> str:
            return f"echo: {message}"

        # Build ASGI request to /mcp
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "echo", "arguments": {"message": "test"}},
            }
        ).encode("utf-8")

        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status = 0
        response_body = b""

        async def send(message):
            nonlocal status, response_body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")

        scope: dict[str, Any] = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        }

        await app(scope, receive, send)

        assert status == 200
        result = json.loads(response_body)
        assert result["id"] == 1
        content = result["result"]["content"]
        assert content[0]["text"] == "echo: test"

    @pytest.mark.asyncio
    async def test_mcp_not_intercepted_without_tools(self) -> None:
        """If no tools are registered, /mcp falls through to normal routing."""
        app = App()

        @app.route("/mcp")
        def mcp_page():
            return "This is a regular page"

        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        status = 0
        response_body = b""

        async def send(message):
            nonlocal status, response_body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")

        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/mcp",
            "headers": [],
            "query_string": b"",
        }

        await app(scope, receive, send)

        assert status == 200
        assert b"This is a regular page" in response_body

    @pytest.mark.asyncio
    async def test_middleware_applies_to_mcp(self) -> None:
        """Middleware runs on MCP requests (auth, CORS, etc.)."""
        app = App()
        middleware_called = False

        async def tracking_middleware(request, next):
            nonlocal middleware_called
            middleware_called = True
            response = await next(request)
            return response.with_header("X-Middleware", "applied")

        app.add_middleware(tracking_middleware)

        @app.route("/")
        def index():
            return "hello"

        @app.tool("echo", description="Echo")
        def echo(message: str) -> str:
            return message

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {},
            }
        ).encode("utf-8")

        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status = 0
        response_body = b""
        response_headers: list[tuple[bytes, bytes]] = []

        async def send(message):
            nonlocal status, response_body
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers.extend(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")

        scope: dict[str, Any] = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        }

        await app(scope, receive, send)

        assert status == 200
        assert middleware_called
        # Check the middleware header was applied
        header_dict = dict(response_headers)
        assert header_dict.get(b"x-middleware") == b"applied"

    @pytest.mark.asyncio
    async def test_configurable_mcp_path(self) -> None:
        """MCP endpoint respects AppConfig.mcp_path."""
        config = AppConfig(mcp_path="/api/mcp")
        app = App(config=config)

        @app.route("/")
        def index():
            return "hello"

        @app.tool("echo", description="Echo")
        def echo(message: str) -> str:
            return message

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
                "params": {},
            }
        ).encode("utf-8")

        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status = 0
        response_body = b""

        async def send(message):
            nonlocal status, response_body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")

        # Hit the custom path
        scope: dict[str, Any] = {
            "type": "http",
            "method": "POST",
            "path": "/api/mcp",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        }

        await app(scope, receive, send)

        assert status == 200
        result = json.loads(response_body)
        assert "tools" in result["result"]

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_closes_event_bus(self) -> None:
        """Lifespan shutdown calls ToolEventBus.close()."""
        app = App()

        @app.route("/")
        def index():
            return "hello"

        @app.tool("echo", description="Echo")
        def echo(message: str) -> str:
            return message

        # Start a subscriber
        subscriber_done = False

        async def subscriber():
            nonlocal subscriber_done
            async for _event in app.tool_events.subscribe():
                pass
            subscriber_done = True

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Simulate lifespan startup + shutdown
        messages = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive():
            return next(messages)

        sends: list[dict] = []

        async def send(message):
            sends.append(message)

        await app({"type": "lifespan"}, receive, send)

        # The subscriber should have been signaled to stop
        await asyncio.wait_for(task, timeout=2.0)
        assert subscriber_done

        # Verify lifespan completed normally
        send_types = [s["type"] for s in sends]
        assert "lifespan.startup.complete" in send_types
        assert "lifespan.shutdown.complete" in send_types

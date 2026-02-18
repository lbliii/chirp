"""Tests for chirp.tools — MCP tool registration, schema, events, and protocol."""

import asyncio
import json
import time
from typing import Any

import pytest

from chirp.app import App
from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import ToolDef, ToolRegistry, compile_tools
from chirp.tools.schema import function_to_schema

# =============================================================================
# Schema generation tests
# =============================================================================


class TestFunctionToSchema:
    def test_no_params(self) -> None:
        def func() -> str:
            return "hello"

        schema = function_to_schema(func)
        assert schema == {"type": "object", "properties": {}}

    def test_basic_types(self) -> None:
        def func(name: str, count: int, rate: float, active: bool) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["count"] == {"type": "integer"}
        assert schema["properties"]["rate"] == {"type": "number"}
        assert schema["properties"]["active"] == {"type": "boolean"}
        assert sorted(schema["required"]) == ["active", "count", "name", "rate"]

    def test_optional_with_default(self) -> None:
        def func(query: str, limit: int = 10) -> None:
            pass

        schema = function_to_schema(func)
        assert "query" in schema["required"]
        assert "limit" not in schema.get("required", [])

    def test_optional_union_none(self) -> None:
        def func(query: str, category: str | None = None) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["category"] == {"type": "string"}
        assert "category" not in schema.get("required", [])

    def test_list_type(self) -> None:
        def func(tags: list[str]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}

    def test_list_int(self) -> None:
        def func(ids: list[int]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["ids"] == {"type": "array", "items": {"type": "integer"}}

    def test_dict_type(self) -> None:
        def func(metadata: dict[str, Any]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["metadata"] == {"type": "object"}

    def test_request_param_excluded(self) -> None:
        """Parameters named 'request' or annotated as Request are excluded."""

        def func(request: Request, query: str) -> None:
            pass

        schema = function_to_schema(func)
        assert "request" not in schema["properties"]
        assert "query" in schema["properties"]

    def test_request_by_name_excluded(self) -> None:
        def func(request: Any, query: str) -> None:
            pass

        schema = function_to_schema(func)
        assert "request" not in schema["properties"]

    def test_unannotated_defaults_to_string(self) -> None:
        def func(name) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"] == {"type": "string"}

    def test_async_function(self) -> None:
        async def func(query: str, limit: int = 10) -> list[dict]:
            return []

        schema = function_to_schema(func)
        assert schema["properties"]["query"] == {"type": "string"}
        assert schema["properties"]["limit"] == {"type": "integer"}
        assert schema["required"] == ["query"]


# =============================================================================
# ToolDef tests
# =============================================================================


class TestToolDef:
    def test_frozen(self) -> None:
        def handler() -> str:
            return "ok"

        tool = ToolDef(name="test", description="A test", handler=handler, schema={})
        with pytest.raises(AttributeError):
            tool.name = "other"  # type: ignore[misc]

    def test_fields(self) -> None:
        def handler() -> str:
            return "ok"

        tool = ToolDef(
            name="search",
            description="Search things",
            handler=handler,
            schema={"type": "object", "properties": {}},
        )
        assert tool.name == "search"
        assert tool.description == "Search things"
        assert tool.handler is handler


# =============================================================================
# ToolRegistry tests
# =============================================================================


class TestToolRegistry:
    def _make_registry(
        self,
        tools: list[tuple[str, str, Any]] | None = None,
    ) -> ToolRegistry:
        bus = ToolEventBus()
        if tools is None:
            tools = [
                ("search", "Search items", self._search_handler),
                ("create", "Create item", self._create_handler),
            ]
        return compile_tools(tools, bus)

    async def _search_handler(self, query: str) -> list[dict]:
        return [{"name": "item1", "query": query}]

    async def _create_handler(self, title: str, body: str = "") -> dict:
        return {"title": title, "body": body}

    def test_list_tools(self) -> None:
        registry = self._make_registry()
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"search", "create"}

    def test_list_tools_format(self) -> None:
        registry = self._make_registry()
        tools = registry.list_tools()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_contains(self) -> None:
        registry = self._make_registry()
        assert "search" in registry
        assert "missing" not in registry

    def test_len(self) -> None:
        registry = self._make_registry()
        assert len(registry) == 2

    def test_get(self) -> None:
        registry = self._make_registry()
        tool = registry.get("search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_missing(self) -> None:
        registry = self._make_registry()
        assert registry.get("nope") is None

    @pytest.mark.asyncio
    async def test_call_tool(self) -> None:
        async def search(query: str) -> list[dict]:
            return [{"q": query}]

        registry = self._make_registry([("search", "Search", search)])
        result = await registry.call_tool("search", {"query": "test"})
        assert result == [{"q": "test"}]

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self) -> None:
        registry = self._make_registry([])
        with pytest.raises(KeyError, match="Tool not found"):
            await registry.call_tool("missing", {})

    @pytest.mark.asyncio
    async def test_call_sync_tool(self) -> None:
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        registry = self._make_registry([("greet", "Greet", greet)])
        result = await registry.call_tool("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_duplicate_name_raises(self) -> None:
        def handler() -> str:
            return "ok"

        with pytest.raises(ValueError, match="Duplicate tool name"):
            compile_tools(
                [("test", "Test", handler), ("test", "Test 2", handler)],
                ToolEventBus(),
            )


# =============================================================================
# ToolEventBus tests
# =============================================================================


class TestToolEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def collector():
            async for event in bus.subscribe():
                received.append(event)
                if len(received) >= 2:
                    break

        event1 = ToolCallEvent(
            tool_name="search",
            arguments={"q": "test"},
            result=[],
            timestamp=time.time(),
        )
        event2 = ToolCallEvent(
            tool_name="create",
            arguments={"title": "hi"},
            result={"id": 1},
            timestamp=time.time(),
        )

        task = asyncio.create_task(collector())
        # Give the subscriber time to register
        await asyncio.sleep(0.01)

        await bus.emit(event1)
        await bus.emit(event2)

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == 2
        assert received[0].tool_name == "search"
        assert received[1].tool_name == "create"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        bus = ToolEventBus()
        received_a: list[ToolCallEvent] = []
        received_b: list[ToolCallEvent] = []

        async def collector_a():
            async for event in bus.subscribe():
                received_a.append(event)
                if len(received_a) >= 1:
                    break

        async def collector_b():
            async for event in bus.subscribe():
                received_b.append(event)
                if len(received_b) >= 1:
                    break

        task_a = asyncio.create_task(collector_a())
        task_b = asyncio.create_task(collector_b())
        await asyncio.sleep(0.01)

        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=time.time(),
        )
        await bus.emit(event)

        await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=2.0)
        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        bus = ToolEventBus()
        count = 0

        async def collector():
            nonlocal count
            async for _event in bus.subscribe():
                count += 1

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        assert count == 0

    def test_event_frozen(self) -> None:
        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=1234.0,
        )
        with pytest.raises(AttributeError):
            event.tool_name = "other"  # type: ignore[misc]

    def test_event_call_id_generated(self) -> None:
        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=1234.0,
        )
        assert isinstance(event.call_id, str)
        assert len(event.call_id) == 12


# =============================================================================
# ToolRegistry event emission tests
# =============================================================================


class TestToolRegistryEvents:
    @pytest.mark.asyncio
    async def test_call_emits_event(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def search(query: str) -> list[str]:
            return ["result1"]

        registry = compile_tools([("search", "Search", search)], bus)

        async def collector():
            async for event in bus.subscribe():
                received.append(event)
                break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await registry.call_tool("search", {"query": "test"})
        assert result == ["result1"]

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == 1
        assert received[0].tool_name == "search"
        assert received[0].arguments == {"query": "test"}
        assert received[0].result == ["result1"]


# =============================================================================
# MCP handler tests (Request/Response level)
# =============================================================================


def _make_request(
    *,
    method: str = "POST",
    path: str = "/mcp",
    body: dict | bytes | None = None,
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

    return Request.from_asgi(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"content-type", b"application/json")],
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
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["id"] == 1
        assert "protocolVersion" in body["result"]
        assert "capabilities" in body["result"]
        assert "tools" in body["result"]["capabilities"]

    @pytest.mark.asyncio
    async def test_tools_list(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "tools/list", "id": 2, "params": {}},
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
            body={"jsonrpc": "2.0", "method": "tools/list", "id": 3, "params": {}},
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
                "params": {"name": "greet", "arguments": {"name": "World"}},
            }
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
                "params": {"name": "search", "arguments": {"query": "test"}},
            }
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
                "params": {"name": "missing", "arguments": {}},
            }
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
                "params": {},
            }
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
        response = await handle_mcp_request(request, registry)
        assert response.status == 204


# =============================================================================
# App integration tests
# =============================================================================


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

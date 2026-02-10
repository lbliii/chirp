"""Async test client for chirp applications.

Uses the same Request and Response types as production.
No wrapper translation layer.
"""

import asyncio
import contextlib
import inspect
from typing import Any

from chirp.app import App
from chirp.http.response import Response
from chirp.testing.sse import SSETestResult, parse_sse_frames


class TestClient:
    __test__ = False  # Tell pytest this is not a test class
    """Async test client for chirp applications.

    Returns the same ``Response`` type used in production. Sends requests
    through the ASGI interface directly — no HTTP involved.

    Usage::

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
    """

    __slots__ = ("app",)

    def __init__(self, app: App) -> None:
        self.app = app

    async def __aenter__(self) -> TestClient:
        self.app._ensure_frozen()

        # Mirror lifespan database setup (connect, set accessor, migrate).
        # This matches the behaviour in App._handle_lifespan so that
        # apps using App(db=..., migrations=...) work under TestClient.
        if self.app._db is not None:
            await self.app._db.connect()
            from chirp.data.database import _db_var

            _db_var.set(self.app._db)
            if self.app._migrations_dir is not None:
                from chirp.data.migrate import migrate

                await migrate(self.app._db, self.app._migrations_dir)

        for hook in self.app._startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
        return self

    async def __aexit__(self, *args: object) -> None:
        for hook in self.app._shutdown_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result

        # Mirror lifespan database teardown.
        if self.app._db is not None:
            await self.app._db.disconnect()

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ) -> Response:
        """Send a GET request."""
        return await self.request("GET", path, headers=headers)

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        json: dict[str, object] | None = None,
    ) -> Response:
        """Send a POST request."""
        extra_headers: dict[str, str] = {}
        request_body = body or b""

        if json is not None:
            import json as json_module

            request_body = json_module.dumps(json).encode("utf-8")
            extra_headers["content-type"] = "application/json"

        merged = {**extra_headers, **(headers or {})}
        return await self.request("POST", path, headers=merged, body=request_body)

    async def put(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send a PUT request."""
        return await self.request("PUT", path, headers=headers, body=body)

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send a DELETE request."""
        return await self.request("DELETE", path, headers=headers)

    async def fragment(
        self,
        path: str,
        *,
        method: str = "GET",
        target: str | None = None,
        trigger: str | None = None,
        history_restore: bool = False,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send a fragment request (sets HX-Request header).

        Args:
            path: The URL path to request.
            method: HTTP method (default GET).
            target: Sets the ``HX-Target`` header (element ID being targeted).
            trigger: Sets the ``HX-Trigger`` header (element that triggered).
            history_restore: If True, sets ``HX-History-Restore-Request: true``
                to simulate a back/forward navigation cache miss.
            headers: Additional headers to include.
            body: Request body bytes (for POST/PUT).
        """
        fragment_headers: dict[str, str] = {"HX-Request": "true"}
        if target is not None:
            fragment_headers["HX-Target"] = target
        if trigger is not None:
            fragment_headers["HX-Trigger"] = trigger
        if history_restore:
            fragment_headers["HX-History-Restore-Request"] = "true"
        if headers:
            fragment_headers.update(headers)
        return await self.request(method, path, headers=fragment_headers, body=body)

    async def sse(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        max_events: int = 10,
        disconnect_after: float | None = None,
        timeout: float | None = None,
    ) -> SSETestResult:
        """Connect to an SSE endpoint and collect events.

        The connection stays open until one of:

        - ``max_events`` data events have been collected, or
        - ``disconnect_after`` (or ``timeout``) seconds have elapsed, or
        - the server closes the stream (generator exhausted).

        ``timeout`` is an alias for ``disconnect_after``.

        Returns an ``SSETestResult`` with parsed events and metadata.

        Usage::

            result = await client.sse("/notifications", max_events=3)
            assert len(result.events) == 3
            assert result.events[0].data == "hello"
        """
        if timeout is not None and disconnect_after is not None:
            msg = "Cannot specify both 'timeout' and 'disconnect_after'."
            raise TypeError(msg)
        if timeout is not None:
            disconnect_after = timeout
        # Split path and query string
        if "?" in path:
            path_part, query_string = path.split("?", 1)
        else:
            path_part = path
            query_string = ""

        # Build raw ASGI headers
        raw_headers: list[tuple[bytes, bytes]] = [
            (b"accept", b"text/event-stream"),
        ]
        for name, value in (headers or {}).items():
            raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": path_part,
            "raw_path": path_part.encode("latin-1"),
            "query_string": query_string.encode("latin-1"),
            "root_path": "",
            "headers": raw_headers,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 0),
        }

        # Disconnect control: blocks receive() until we want to disconnect.
        # Key invariant: setting disconnect_trigger causes monitor_disconnect()
        # in handle_sse to receive http.disconnect, which cancels the producer.
        disconnect_trigger = asyncio.Event()
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            # Block until disconnect is triggered
            await disconnect_trigger.wait()
            return {"type": "http.disconnect"}

        # Capture response
        response_status = 200
        response_headers_raw: list[tuple[bytes, bytes]] = []
        body_buffer: list[bytes] = []
        event_count = 0

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, event_count
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers_raw.extend(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    body_buffer.append(chunk)
                    # Count data events in this chunk
                    text = chunk.decode("utf-8", errors="replace")
                    for block in text.split("\n\n"):
                        block = block.strip()
                        if not block:
                            continue
                        if any(line.startswith("data: ") for line in block.split("\n")):
                            event_count += 1
                    # Trigger disconnect when we have enough events.
                    # The sleep(0) is critical: it yields to the event loop so
                    # monitor_disconnect() can process the trigger. Without it,
                    # a fast generator + synchronous send creates a tight loop
                    # that starves the event loop.
                    if event_count >= max_events and not disconnect_trigger.is_set():
                        disconnect_trigger.set()
                        await asyncio.sleep(0)

        # Run the ASGI app as a task
        app_task = asyncio.create_task(self.app(scope, receive, send))

        try:
            if disconnect_after is not None:
                # Time-based disconnect: sleep, then trigger
                await asyncio.sleep(disconnect_after)
                disconnect_trigger.set()

            # Wait for the app to finish (either generator exhausted
            # or disconnect processed by the SSE handler)
            timeout = (disconnect_after or 0) + 5.0
            await asyncio.wait_for(app_task, timeout=timeout)
        except TimeoutError:
            # Safety net: force-cancel if the app didn't shut down in time
            disconnect_trigger.set()
            app_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app_task
        except Exception:
            # Suppress errors from the app task (e.g. generator exceptions)
            # — the events collected before the error are still useful.
            if not app_task.done():
                disconnect_trigger.set()
                app_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await app_task

        # Parse collected SSE data
        raw_text = b"".join(body_buffer).decode("utf-8", errors="replace")
        events, heartbeats = parse_sse_frames(raw_text)

        # Build response headers dict
        resp_headers: dict[str, str] = {}
        for name_b, value_b in response_headers_raw:
            resp_headers[name_b.decode("latin-1")] = value_b.decode("latin-1")

        return SSETestResult(
            events=tuple(events),
            heartbeats=heartbeats,
            status=response_status,
            headers=resp_headers,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send an arbitrary request through the ASGI app."""
        # Split path and query string
        if "?" in path:
            path_part, query_string = path.split("?", 1)
        else:
            path_part = path
            query_string = ""

        # Build raw ASGI headers
        raw_headers: list[tuple[bytes, bytes]] = []
        for name, value in (headers or {}).items():
            raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

        # Build ASGI scope
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "path": path_part,
            "raw_path": path_part.encode("latin-1"),
            "query_string": query_string.encode("latin-1"),
            "root_path": "",
            "headers": raw_headers,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 0),
        }

        # Build receive callable
        request_body = body or b""
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            # After body is sent, wait for disconnect (simplified)
            return {"type": "http.disconnect"}

        # Capture response via send
        response_started = False
        response_status = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_body_parts: list[bytes] = []

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started, response_status, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body_parts.append(message.get("body", b""))

        # Call the ASGI app
        await self.app(scope, receive, send)

        # Build chirp Response from captured data
        body_bytes = b"".join(response_body_parts)

        # Extract content-type from headers
        content_type = "text/html; charset=utf-8"
        extra_headers: list[tuple[str, str]] = []
        for name_b, value_b in response_headers:
            name_str = name_b.decode("latin-1")
            value_str = value_b.decode("latin-1")
            if name_str == "content-type":
                content_type = value_str
            elif name_str != "content-length":
                extra_headers.append((name_str, value_str))

        return Response(
            body=body_bytes,
            status=response_status,
            content_type=content_type,
            headers=tuple(extra_headers),
        )

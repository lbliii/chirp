"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import asyncio
from typing import Any

import pytest

from chirp import App
from chirp.testing import TestClient


async def _lifespan_exchange(
    app: App,
) -> tuple[list[dict[str, Any]], bool]:
    """Drive the full lifespan protocol and return messages sent by the app.

    Returns (sent_messages, startup_ok).
    """
    sent: list[dict[str, Any]] = []
    receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive() -> dict[str, Any]:
        return await receive_queue.get()

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "lifespan",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
    }

    # Start the lifespan handler as a background task
    task = asyncio.create_task(app(scope, receive, send))

    # Send startup
    await receive_queue.put({"type": "lifespan.startup"})
    # Give the task a chance to process
    await asyncio.sleep(0.01)

    startup_ok = any(m["type"] == "lifespan.startup.complete" for m in sent)

    if startup_ok:
        # Send shutdown
        await receive_queue.put({"type": "lifespan.shutdown"})
        await asyncio.wait_for(task, timeout=2.0)

    else:
        # Startup failed — task should have returned already
        await asyncio.wait_for(task, timeout=2.0)

    return sent, startup_ok


class TestLifespanRegistration:
    """on_startup / on_shutdown decorators store hooks correctly."""

    def test_on_startup_stores_hook(self) -> None:
        app = App()

        @app.on_startup
        async def setup():
            pass

        assert len(app._startup_hooks) == 1
        assert app._startup_hooks[0] is setup

    def test_on_shutdown_stores_hook(self) -> None:
        app = App()

        @app.on_shutdown
        async def teardown():
            pass

        assert len(app._shutdown_hooks) == 1
        assert app._shutdown_hooks[0] is teardown

    def test_multiple_hooks_preserve_order(self) -> None:
        app = App()
        order: list[str] = []

        @app.on_startup
        async def first():
            order.append("first")

        @app.on_startup
        async def second():
            order.append("second")

        assert app._startup_hooks == [first, second]

    def test_cannot_register_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.on_startup
            async def late():
                pass

    def test_cannot_register_shutdown_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.on_shutdown
            async def late():
                pass

    def test_returns_original_function(self) -> None:
        app = App()

        @app.on_startup
        async def setup():
            pass

        # Decorator should return the function unchanged
        assert callable(setup)
        assert setup.__name__ == "setup"


class TestLifespanProtocol:
    """Full ASGI lifespan protocol via raw scope/receive/send."""

    async def test_happy_path(self) -> None:
        """Startup hooks run, complete sent, shutdown hooks run, complete sent."""
        app = App()
        events: list[str] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_startup
        async def setup():
            events.append("startup")

        @app.on_shutdown
        async def teardown():
            events.append("shutdown")

        sent, ok = await _lifespan_exchange(app)

        assert ok is True
        assert events == ["startup", "shutdown"]
        types = [m["type"] for m in sent]
        assert "lifespan.startup.complete" in types
        assert "lifespan.shutdown.complete" in types

    async def test_startup_failure(self) -> None:
        """Hook raises — startup.failed sent with error message."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        @app.on_startup
        async def bad_setup():
            msg = "Database connection refused"
            raise ConnectionError(msg)

        sent, ok = await _lifespan_exchange(app)

        assert ok is False
        failed = [m for m in sent if m["type"] == "lifespan.startup.failed"]
        assert len(failed) == 1
        assert "Database connection refused" in failed[0]["message"]

    async def test_no_hooks(self) -> None:
        """Lifespan responds correctly even with no hooks registered."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        sent, ok = await _lifespan_exchange(app)

        assert ok is True
        types = [m["type"] for m in sent]
        assert "lifespan.startup.complete" in types
        assert "lifespan.shutdown.complete" in types

    async def test_sync_hooks(self) -> None:
        """Sync (non-async) hooks work correctly."""
        app = App()
        events: list[str] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_startup
        def sync_setup():
            events.append("sync_startup")

        @app.on_shutdown
        def sync_teardown():
            events.append("sync_shutdown")

        _sent, ok = await _lifespan_exchange(app)

        assert ok is True
        assert events == ["sync_startup", "sync_shutdown"]

    async def test_multiple_hooks_run_in_order(self) -> None:
        """Multiple hooks run in registration order."""
        app = App()
        order: list[int] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_startup
        async def first():
            order.append(1)

        @app.on_startup
        async def second():
            order.append(2)

        @app.on_startup
        async def third():
            order.append(3)

        _sent, ok = await _lifespan_exchange(app)

        assert ok is True
        assert order == [1, 2, 3]

    async def test_app_is_frozen_at_startup(self) -> None:
        """The app is frozen during lifespan startup, not on first HTTP request."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        assert app._frozen is False
        _sent, ok = await _lifespan_exchange(app)
        assert ok is True
        assert app._frozen is True


class TestLifespanTestClient:
    """Hooks fire during async with TestClient(app)."""

    async def test_startup_hooks_run_on_enter(self) -> None:
        app = App()
        started = False

        @app.route("/")
        def index():
            return "ok"

        @app.on_startup
        async def setup():
            nonlocal started
            started = True

        assert started is False
        async with TestClient(app):
            assert started is True

    async def test_shutdown_hooks_run_on_exit(self) -> None:
        app = App()
        stopped = False

        @app.route("/")
        def index():
            return "ok"

        @app.on_shutdown
        async def teardown():
            nonlocal stopped
            stopped = True

        async with TestClient(app):
            assert stopped is False
        assert stopped is True

    async def test_state_visible_during_requests(self) -> None:
        """State set in startup hook is visible during request handling."""
        app = App()
        db: dict[str, str] = {}

        @app.on_startup
        async def seed():
            db["status"] = "ready"

        @app.route("/status")
        def status():
            return db.get("status", "not ready")

        @app.on_shutdown
        async def cleanup():
            db.clear()

        async with TestClient(app) as client:
            response = await client.get("/status")
            assert response.text == "ready"

        # Shutdown hook cleared the state
        assert db == {}

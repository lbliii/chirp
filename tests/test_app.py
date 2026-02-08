"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import asyncio
from typing import Any

import pytest

from chirp.app import App
from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.testing import TestClient


class TestAppRegistration:
    def test_route_decorator(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        assert len(app._pending_routes) == 1
        assert app._pending_routes[0].path == "/"

    def test_route_with_methods(self) -> None:
        app = App()

        @app.route("/users", methods=["GET", "POST"])
        def users():
            return "users"

        assert app._pending_routes[0].methods == ["GET", "POST"]

    def test_error_decorator(self) -> None:
        app = App()

        @app.error(404)
        def not_found():
            return "Not found"

        assert 404 in app._error_handlers

    def test_middleware_registration(self) -> None:
        app = App()

        async def my_mw(request, next):
            return await next(request)

        app.add_middleware(my_mw)
        assert len(app._middleware_list) == 1

    def test_template_filter(self) -> None:
        app = App()

        @app.template_filter()
        def currency(value: float) -> str:
            return f"${value:,.2f}"

        assert "currency" in app._template_filters

    def test_template_filter_custom_name(self) -> None:
        app = App()

        @app.template_filter(name="money")
        def currency(value: float) -> str:
            return f"${value:,.2f}"

        assert "money" in app._template_filters

    def test_template_global(self) -> None:
        app = App()

        @app.template_global()
        def site_name() -> str:
            return "My App"

        assert "site_name" in app._template_globals


class TestAppFreeze:
    def test_freeze_compiles_router(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        app._ensure_frozen()
        assert app._frozen is True
        assert app._router is not None

    def test_cannot_add_routes_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.route("/")
            def index():
                return "hello"

    def test_cannot_add_middleware_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        async def mw(request, next):
            return await next(request)

        with pytest.raises(RuntimeError, match="Cannot modify"):
            app.add_middleware(mw)

    def test_double_freeze_is_safe(self) -> None:
        app = App()
        app._ensure_frozen()
        app._ensure_frozen()  # Should not raise
        assert app._frozen is True


class TestAppConfig:
    def test_default_config(self) -> None:
        app = App()
        assert app.config.host == "127.0.0.1"
        assert app.config.port == 8000

    def test_custom_config(self) -> None:
        cfg = AppConfig(host="0.0.0.0", port=3000, debug=True)
        app = App(config=cfg)
        assert app.config.host == "0.0.0.0"
        assert app.config.debug is True


class TestAppE2E:
    """End-to-end tests using TestClient."""

    async def test_hello_world(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "Hello, World!"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert response.text == "Hello, World!"

    async def test_json_response(self) -> None:
        app = App()

        @app.route("/api/data")
        def data():
            return {"message": "hello", "count": 42}

        async with TestClient(app) as client:
            response = await client.get("/api/data")
            assert response.status == 200
            assert "application/json" in response.content_type

    async def test_path_params(self) -> None:
        app = App()

        @app.route("/users/{name}")
        def user(name: str):
            return f"Hello, {name}!"

        async with TestClient(app) as client:
            response = await client.get("/users/alice")
            assert response.status == 200
            assert response.text == "Hello, alice!"

    async def test_typed_path_params(self) -> None:
        app = App()

        @app.route("/users/{id:int}")
        def user(id: int):
            return {"id": id}

        async with TestClient(app) as client:
            response = await client.get("/users/42")
            assert response.status == 200
            assert "42" in response.text

    async def test_multiple_methods(self) -> None:
        app = App()

        @app.route("/items", methods=["GET"])
        def list_items():
            return "item list"

        @app.route("/items", methods=["POST"])
        def create_item():
            return ("created", 201)

        async with TestClient(app) as client:
            get_resp = await client.get("/items")
            assert get_resp.status == 200

            post_resp = await client.post("/items")
            assert post_resp.status == 201

    async def test_404_default(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404

    async def test_405_default(self) -> None:
        app = App()

        @app.route("/items", methods=["GET"])
        def items():
            return "items"

        async with TestClient(app) as client:
            response = await client.post("/items")
            assert response.status == 405

    async def test_async_handler(self) -> None:
        app = App()

        @app.route("/async")
        async def async_handler():
            return "async works"

        async with TestClient(app) as client:
            response = await client.get("/async")
            assert response.status == 200
            assert response.text == "async works"

    async def test_request_injection(self) -> None:
        app = App()

        @app.route("/echo")
        async def echo(request: Request):
            return f"method={request.method} path={request.path}"

        async with TestClient(app) as client:
            response = await client.get("/echo")
            assert "method=GET" in response.text
            assert "path=/echo" in response.text

    async def test_response_chaining(self) -> None:
        app = App()

        @app.route("/custom")
        def custom():
            return Response("Created").with_status(201).with_header("X-Custom", "yes")

        async with TestClient(app) as client:
            response = await client.get("/custom")
            assert response.status == 201

    async def test_redirect(self) -> None:
        from chirp.http.response import Redirect

        app = App()

        @app.route("/old")
        def old():
            return Redirect("/new")

        async with TestClient(app) as client:
            response = await client.get("/old")
            assert response.status == 302

    async def test_middleware(self) -> None:
        app = App()

        async def add_header(request: Request, next):
            response = await next(request)
            return response.with_header("x-middleware", "applied")

        app.add_middleware(add_header)

        @app.route("/")
        def index():
            return "hello"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert ("x-middleware", "applied") in response.headers

    async def test_fragment_request(self) -> None:
        app = App()

        @app.route("/search")
        def search(request: Request):
            if request.is_fragment:
                return "fragment only"
            return "full page"

        async with TestClient(app) as client:
            full = await client.get("/search")
            assert full.text == "full page"

            fragment = await client.fragment("/search")
            assert fragment.text == "fragment only"

    async def test_tuple_status_override(self) -> None:
        app = App()

        @app.route("/created")
        def created():
            return ("Resource created", 201)

        async with TestClient(app) as client:
            response = await client.get("/created")
            assert response.status == 201
            assert response.text == "Resource created"


# ---------------------------------------------------------------------------
# Lifespan registration
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Lifespan ASGI protocol
# ---------------------------------------------------------------------------


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

        sent, ok = await _lifespan_exchange(app)

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

        sent, ok = await _lifespan_exchange(app)

        assert ok is True
        assert order == [1, 2, 3]

    async def test_app_is_frozen_at_startup(self) -> None:
        """The app is frozen during lifespan startup, not on first HTTP request."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        assert app._frozen is False
        sent, ok = await _lifespan_exchange(app)
        assert ok is True
        assert app._frozen is True


# ---------------------------------------------------------------------------
# Lifespan via TestClient
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Per-worker lifecycle hooks — registration
# ---------------------------------------------------------------------------


class TestWorkerLifecycleRegistration:
    """on_worker_startup / on_worker_shutdown decorators store hooks."""

    def test_on_worker_startup_stores_hook(self) -> None:
        app = App()

        @app.on_worker_startup
        async def create_client():
            pass

        assert len(app._worker_startup_hooks) == 1
        assert app._worker_startup_hooks[0] is create_client

    def test_on_worker_shutdown_stores_hook(self) -> None:
        app = App()

        @app.on_worker_shutdown
        async def close_client():
            pass

        assert len(app._worker_shutdown_hooks) == 1
        assert app._worker_shutdown_hooks[0] is close_client

    def test_multiple_hooks_preserve_order(self) -> None:
        app = App()

        @app.on_worker_startup
        async def first():
            pass

        @app.on_worker_startup
        async def second():
            pass

        assert app._worker_startup_hooks == [first, second]

    def test_cannot_register_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.on_worker_startup
            async def late():
                pass

    def test_cannot_register_shutdown_after_freeze(self) -> None:
        app = App()
        app._ensure_frozen()

        with pytest.raises(RuntimeError, match="Cannot modify"):

            @app.on_worker_shutdown
            async def late():
                pass

    def test_returns_original_function(self) -> None:
        app = App()

        @app.on_worker_startup
        async def create_client():
            pass

        assert callable(create_client)
        assert create_client.__name__ == "create_client"


# ---------------------------------------------------------------------------
# Per-worker lifecycle hooks — dispatch via scope types
# ---------------------------------------------------------------------------


class TestWorkerLifecycleDispatch:
    """App dispatches pounce.worker.startup/shutdown scopes to hooks."""

    async def test_worker_startup_runs_hooks(self) -> None:
        app = App()
        events: list[str] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        async def setup():
            events.append("worker_startup")

        # Simulate pounce sending the worker startup scope
        await app(
            {"type": "pounce.worker.startup", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )

        assert events == ["worker_startup"]

    async def test_worker_shutdown_runs_hooks(self) -> None:
        app = App()
        events: list[str] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_shutdown
        async def teardown():
            events.append("worker_shutdown")

        await app(
            {"type": "pounce.worker.shutdown", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )

        assert events == ["worker_shutdown"]

    async def test_worker_hooks_run_in_order(self) -> None:
        app = App()
        order: list[int] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        async def first():
            order.append(1)

        @app.on_worker_startup
        async def second():
            order.append(2)

        @app.on_worker_startup
        async def third():
            order.append(3)

        await app(
            {"type": "pounce.worker.startup", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )

        assert order == [1, 2, 3]

    async def test_sync_worker_hooks(self) -> None:
        app = App()
        events: list[str] = []

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        def sync_setup():
            events.append("sync_worker_startup")

        @app.on_worker_shutdown
        def sync_teardown():
            events.append("sync_worker_shutdown")

        await app(
            {"type": "pounce.worker.startup", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )
        await app(
            {"type": "pounce.worker.shutdown", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )

        assert events == ["sync_worker_startup", "sync_worker_shutdown"]

    async def test_no_hooks_registered(self) -> None:
        """Worker scopes complete without error when no hooks registered."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        # Should not raise
        await app(
            {"type": "pounce.worker.startup", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )
        await app(
            {"type": "pounce.worker.shutdown", "worker_id": 0},
            _dummy_receive,
            _dummy_send,
        )

    async def test_worker_startup_error_propagates(self) -> None:
        """Errors in worker startup hooks propagate (pounce catches them)."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        async def bad_setup():
            msg = "Cannot connect to database"
            raise ConnectionError(msg)

        with pytest.raises(ConnectionError, match="Cannot connect"):
            await app(
                {"type": "pounce.worker.startup", "worker_id": 0},
                _dummy_receive,
                _dummy_send,
            )


# Minimal receive/send for testing worker lifecycle scopes

async def _dummy_receive() -> dict[str, Any]:
    return {"type": "http.disconnect"}


async def _dummy_send(message: dict[str, Any]) -> None:
    pass

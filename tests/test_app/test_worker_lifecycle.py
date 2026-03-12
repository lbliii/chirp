"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

from typing import Any

import pytest

from chirp import App


async def _dummy_receive() -> dict[str, Any]:
    return {"type": "http.disconnect"}


async def _dummy_send(message: dict[str, Any]) -> None:
    pass


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

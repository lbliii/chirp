"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import contextlib
import socket
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.errors import ConfigurationError


def _make_listener() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", 0))
    except PermissionError:
        sock.close()
        pytest.skip("local socket bind is not permitted in this environment")
    sock.listen()
    return sock, int(sock.getsockname()[1])


def _read_http_response(port: int) -> bytes:
    deadline = time.monotonic() + 3.0
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25) as client:
                client.settimeout(1.0)
                client.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                chunks: list[bytes] = []
                while True:
                    try:
                        chunk = client.recv(65536)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                return b"".join(chunks)
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    raise AssertionError("Pounce worker did not accept test connection") from last_error


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


class TestWorkerLifecycleProductionGuard:
    """Production launch rejects worker modes that cannot run worker hooks."""

    def test_sync_worker_mode_rejected_when_worker_hooks_registered(self) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        @app.on_worker_startup
        async def setup():
            pass

        with pytest.raises(ConfigurationError, match="worker_mode='async'"):
            run_production_server(app, worker_mode="sync")

    def test_auto_worker_mode_rejected_when_pounce_resolves_to_sync(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from chirp.server import production

        app = App(config=AppConfig(debug=False))

        @app.on_worker_shutdown
        async def teardown():
            pass

        monkeypatch.setattr(production, "_effective_worker_mode", lambda mode: "sync")

        with pytest.raises(ConfigurationError, match="resolved worker_mode='auto' to sync"):
            production.run_production_server(app, worker_mode="auto")

    @patch("pounce.server.Server")
    def test_async_worker_mode_allowed_when_worker_hooks_registered(
        self, mock_server: MagicMock
    ) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        @app.on_worker_startup
        async def setup():
            pass

        run_production_server(app, worker_mode="async")

        mock_server.assert_called_once()


class TestPounceWorkerLifecycleIntegration:
    """Smoke tests against Pounce worker lifecycle behavior."""

    def test_pounce_async_worker_runs_worker_startup_hook(self) -> None:
        from pounce.config import ServerConfig
        from pounce.worker import Worker

        app = App(config=AppConfig(debug=False))
        started = threading.Event()
        shutdown = threading.Event()
        sock, port = _make_listener()

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        async def setup():
            started.set()

        worker = Worker(
            ServerConfig(
                host="127.0.0.1",
                port=port,
                workers=1,
                worker_mode="async",
                shutdown_timeout=0.5,
            ),
            app,
            sock,
            worker_id=0,
            shutdown_event=shutdown,
        )
        thread = threading.Thread(target=worker.run, name="test-pounce-worker", daemon=True)

        try:
            thread.start()
            assert started.wait(2.0)
        finally:
            shutdown.set()
            thread.join(3.0)
            with contextlib.suppress(OSError):
                sock.close()

        assert not thread.is_alive()

    def test_pounce_worker_startup_failure_is_logged_best_effort(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from pounce.config import ServerConfig
        from pounce.worker import Worker

        app = App(config=AppConfig(debug=False))
        shutdown = threading.Event()
        sock, port = _make_listener()

        @app.route("/")
        def index():
            return "ok"

        @app.on_worker_startup
        async def setup():
            msg = "cannot connect worker resource"
            raise RuntimeError(msg)

        worker = Worker(
            ServerConfig(
                host="127.0.0.1",
                port=port,
                workers=1,
                worker_mode="async",
                shutdown_timeout=0.5,
            ),
            app,
            sock,
            worker_id=0,
            shutdown_event=shutdown,
        )
        thread = threading.Thread(target=worker.run, name="test-pounce-worker", daemon=True)
        caplog.set_level("WARNING", logger="pounce.worker.0")

        try:
            thread.start()
            response = _read_http_response(port)
        finally:
            shutdown.set()
            thread.join(3.0)
            with contextlib.suppress(OSError):
                sock.close()

        assert b"200" in response
        assert b"ok" in response
        assert "Worker startup hook raised" in caplog.text
        assert not thread.is_alive()

"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import contextlib
import socket
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from chirp import App, Request
from chirp.config import AppConfig


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


class TestWorkerLifecycleProductionAdapter:
    """Production launch configures Pounce for registered worker hooks."""

    @patch("pounce.server.Server")
    def test_sync_worker_mode_allows_worker_hooks_with_shutdown_policy(
        self, mock_server: MagicMock
    ) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        @app.on_worker_startup
        async def setup():
            pass

        run_production_server(app, worker_mode="sync")

        config = mock_server.call_args.args[0]
        assert config.worker_startup_failure == "shutdown"

    @patch("pounce.server.Server")
    def test_no_worker_hooks_keep_default_startup_policy(self, mock_server: MagicMock) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        run_production_server(app)

        config = mock_server.call_args.args[0]
        assert config.worker_startup_failure == "ignore"

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


class TestProductionServerConfigMapping:
    """run_production_server forwards proxy / rate-limit knobs into ServerConfig."""

    @patch("pounce.server.Server")
    def test_proxy_and_rate_limit_kwargs_reach_server_config(self, mock_server: MagicMock) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        run_production_server(
            app,
            rate_limit_max_tracked_ips=4_242,
            forwarded_for_trusted_hops=2,
            trusted_proxies=("10.0.0.1", "10.0.0.2"),
        )

        mock_server.assert_called_once()
        config = mock_server.call_args[0][0]
        assert config.rate_limit_max_tracked_ips == 4_242
        assert config.forwarded_for_trusted_hops == 2
        # trusted_proxies lands as pounce ServerConfig.trusted_hosts (a frozenset);
        # pounce DERIVES trusted_hosts_wildcard from "*" membership — not set here.
        assert config.trusted_hosts == frozenset({"10.0.0.1", "10.0.0.2"})
        assert config.trusted_hosts_wildcard is False

    @patch("pounce.server.Server")
    def test_server_config_defaults_match_app_config(self, mock_server: MagicMock) -> None:
        from chirp.server.production import run_production_server

        app = App(config=AppConfig(debug=False))

        run_production_server(app)

        config = mock_server.call_args[0][0]
        assert config.rate_limit_max_tracked_ips == 100_000
        assert config.forwarded_for_trusted_hops == 1
        assert config.trusted_hosts == frozenset()

    @patch("pounce.server.Server")
    def test_request_body_limit_reaches_server_config(self, mock_server: MagicMock) -> None:
        from chirp.server.production import run_production_server

        body_limit = 2 * 1024 * 1024
        app = App(
            config=AppConfig(
                debug=False,
                max_request_body_size=body_limit,
                max_upload_size=body_limit,
            )
        )

        run_production_server(app)

        config = mock_server.call_args.args[0]
        assert config.max_request_size == body_limit


class TestPounceRequestBodyLimitIntegration:
    """The production adapter and real Pounce agree on Chirp's body ceiling."""

    def test_wire_accepts_above_pounce_default_and_rejects_above_chirp_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pounce.server import Server as PounceServer

        from chirp.server.production import run_production_server

        body_limit = 2 * 1024 * 1024
        accepted_body = b"x" * (1024 * 1024 + 1)
        rejected_body = b"x" * (body_limit + 1)
        seen: list[int] = []
        app = App(
            config=AppConfig(
                debug=False,
                worker_mode="async",
                max_request_body_size=body_limit,
                max_upload_size=body_limit,
            )
        )

        @app.route("/upload", methods=["POST"])
        async def upload(request: Request) -> str:
            body = await request.body()
            seen.append(len(body))
            return f"got {len(body)}"

        servers: list[PounceServer] = []
        server_configs: list[Any] = []

        def capture_server(*args: Any, **kwargs: Any) -> PounceServer:
            server_configs.append(args[0])
            server = PounceServer(*args, **kwargs)
            servers.append(server)
            return server

        monkeypatch.setattr("pounce.server.Server", capture_server)
        thread = threading.Thread(
            target=run_production_server,
            kwargs={
                "app": app,
                "host": "127.0.0.1",
                "port": 0,
                "workers": 1,
                "worker_mode": "async",
                "metrics_enabled": False,
                "log_level": "warning",
            },
            daemon=True,
        )

        try:
            thread.start()
            deadline = time.monotonic() + 5.0
            while not servers and time.monotonic() < deadline:
                time.sleep(0.01)
            assert servers, "production adapter did not construct Pounce Server"
            server = servers[0]
            assert server._started_event.wait(5.0)
            assert server.bound_addr is not None
            host, port = server.bound_addr

            accepted = httpx.post(
                f"http://{host}:{port}/upload",
                content=accepted_body,
                trust_env=False,
                timeout=10.0,
            )
            rejected = httpx.post(
                f"http://{host}:{port}/upload",
                content=rejected_body,
                trust_env=False,
                timeout=10.0,
            )
        finally:
            if servers:
                servers[0].shutdown()
            thread.join(5.0)

        assert not thread.is_alive()
        assert server_configs[0].max_request_size == body_limit
        assert accepted.status_code == 200
        assert accepted.text == f"got {len(accepted_body)}"
        assert rejected.status_code == 413
        assert seen == [len(accepted_body)]


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

    def test_pounce_worker_startup_failure_shuts_down_worker(
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
                worker_startup_failure="shutdown",
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

        assert b"200" not in response
        assert "Worker startup hook raised" in caplog.text
        assert not thread.is_alive()

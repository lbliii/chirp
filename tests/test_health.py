"""Health/readiness probes — auto-mounted /health + /ready (#368).

Covers the dormant ``chirp.health`` primitives now wired into the framework:
async ``readiness()``, the ``ready`` startup gate on ``MutableAppState``, the
auto-mounted probe routes (secure-stack + commit-teardown bypass), the
``Database.probe()`` data seam, and the ``deploy_health`` collision contract.
"""

import asyncio
from typing import Any

import pytest

from chirp import App, AppConfig, HealthCheck
from chirp.health import liveness, readiness
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# health.py unit: async readiness aggregates sync + async checks
# ---------------------------------------------------------------------------


async def test_readiness_passes_when_all_checks_ok() -> None:
    async def ok_async() -> bool:
        return True

    ok, failures = await readiness(
        [
            HealthCheck("sync", check=lambda: True),
            HealthCheck("async", check=ok_async),
        ]
    )
    assert ok is True
    assert failures == []


async def test_readiness_collects_sync_and_async_failures() -> None:
    async def bad_async() -> bool:
        return False

    ok, failures = await readiness(
        [
            HealthCheck("cache", check=lambda: False, message="cache down"),
            HealthCheck("db", check=bad_async),
            HealthCheck("ok", check=lambda: True),
        ]
    )
    assert ok is False
    assert "cache down" in failures
    assert "db: unhealthy" in failures
    assert len(failures) == 2


async def test_readiness_catches_raising_check() -> None:
    def boom() -> bool:
        raise RuntimeError("connection refused")

    ok, failures = await readiness([HealthCheck("redis", check=boom)])
    assert ok is False
    assert failures == ["redis: connection refused"]


def test_liveness_is_true() -> None:
    assert liveness() is True


# ---------------------------------------------------------------------------
# Lifecycle: the ready gate flips True after startup, False on shutdown
# ---------------------------------------------------------------------------


async def _lifespan_startup_then_shutdown(
    app: App,
) -> tuple[list[dict[str, Any]], asyncio.Queue[dict[str, Any]], asyncio.Task[None]]:
    sent: list[dict[str, Any]] = []
    receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive() -> dict[str, Any]:
        return await receive_queue.get()

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope: dict[str, Any] = {"type": "lifespan", "asgi": {"version": "3.0"}}
    task = asyncio.create_task(app(scope, receive, send))
    await receive_queue.put({"type": "lifespan.startup"})
    await asyncio.sleep(0.01)
    return sent, receive_queue, task


async def test_ready_flag_false_before_startup() -> None:
    app = App()
    app.freeze()
    assert app._mutable_state.ready is False


async def test_ready_flag_set_after_startup_hooks() -> None:
    app = App()
    order: list[str] = []

    @app.on_startup
    async def hook() -> None:
        # The gate must NOT be set yet when startup hooks run.
        order.append(f"hook ready={app._mutable_state.ready}")

    app.freeze()
    sent, receive_queue, task = await _lifespan_startup_then_shutdown(app)
    assert any(m["type"] == "lifespan.startup.complete" for m in sent)
    assert app._mutable_state.ready is True
    assert order == ["hook ready=False"]

    await receive_queue.put({"type": "lifespan.shutdown"})
    await asyncio.wait_for(task, timeout=2.0)
    assert app._mutable_state.ready is False


async def test_ready_flag_stays_false_when_startup_raises() -> None:
    app = App()

    @app.on_startup
    async def boom() -> None:
        raise RuntimeError("startup failed")

    app.freeze()
    sent, _receive_queue, task = await _lifespan_startup_then_shutdown(app)
    await asyncio.wait_for(task, timeout=2.0)
    assert any(m["type"] == "lifespan.startup.failed" for m in sent)
    assert app._mutable_state.ready is False


# ---------------------------------------------------------------------------
# Registration: add_health_check before/after freeze
# ---------------------------------------------------------------------------


def test_add_health_check_registers() -> None:
    app = App()
    app.add_health_check(HealthCheck("cache", check=lambda: True))
    assert [hc.name for hc in app._mutable_state.health_checks] == ["cache"]


def test_add_health_check_rejects_non_healthcheck() -> None:
    app = App()
    with pytest.raises(TypeError):
        app.add_health_check("not a check")  # type: ignore[arg-type]


def test_add_health_check_raises_after_freeze() -> None:
    app = App()
    app.freeze()
    with pytest.raises(RuntimeError):
        app.add_health_check(HealthCheck("late", check=lambda: True))


# ---------------------------------------------------------------------------
# Database.probe() uses a fresh pooled connection, returns bool
# ---------------------------------------------------------------------------


async def test_database_probe_ok(tmp_path) -> None:
    from chirp.data.database import Database

    db = Database(f"sqlite:///{tmp_path / 'probe.db'}")
    await db.connect()
    try:
        assert await db.probe() is True
    finally:
        await db.disconnect()


async def test_database_probe_does_not_reuse_request_transaction(tmp_path) -> None:
    """probe() acquires a fresh pooled connection, never a live transaction conn."""
    from chirp.data.database import Database, _current_conn

    db = Database(f"sqlite:///{tmp_path / 'probe2.db'}")
    await db.connect()
    try:
        # No transaction is active, so _current_conn is unset and probe takes the
        # pool path. Assert the probe runs without a bound request connection.
        with pytest.raises(LookupError):
            _current_conn.get()
        assert await db.probe() is True
    finally:
        await db.disconnect()


async def test_app_with_db_auto_includes_probe_check(tmp_path) -> None:
    from chirp.data.database import Database

    db = Database(f"sqlite:///{tmp_path / 'auto.db'}")
    app = App(db=db)
    app.freeze()
    assert any(hc.name == "database" for hc in app._mutable_state.health_checks)


# ---------------------------------------------------------------------------
# Contract: deploy_health collision check
# ---------------------------------------------------------------------------


class _Route:
    def __init__(self, path: str) -> None:
        self.path = path


class _Router:
    def __init__(self, paths: list[str]) -> None:
        self.routes = [_Route(p) for p in paths]


def test_health_path_collision_errors() -> None:
    from chirp.contracts.rules_deploy import check_health_path_collision

    cfg = AppConfig(health_path="/health", ready_path="/ready")
    issues = check_health_path_collision(cfg, _Router(["/health", "/"]))
    assert [i.category for i in issues] == ["deploy_health"]
    assert issues[0].severity.name == "ERROR"


def test_ready_path_collision_errors() -> None:
    from chirp.contracts.rules_deploy import check_health_path_collision

    cfg = AppConfig(health_path="/health", ready_path="/ready")
    issues = check_health_path_collision(cfg, _Router(["/ready"]))
    assert [i.category for i in issues] == ["deploy_health"]


def test_health_path_no_collision_ok() -> None:
    from chirp.contracts.rules_deploy import check_health_path_collision

    cfg = AppConfig(health_path="/health", ready_path="/ready")
    assert check_health_path_collision(cfg, _Router(["/", "/about"])) == []


# ---------------------------------------------------------------------------
# Acceptance gate (#368) — the three Success criteria
# ---------------------------------------------------------------------------


@pytest.mark.issue(368)
async def test_auto_mounted_health_and_ready_probes() -> None:
    """#368 success criteria: auto /health 200, /ready gate, secure-stack bypass."""
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    app = App(AppConfig(secret_key="x" * 32))
    # Wire a session so we can prove the probe bypasses it (no Set-Cookie).
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="x" * 32)))

    failing = {"ok": False}

    async def dep() -> bool:
        return failing["ok"]

    app.add_health_check(HealthCheck("dep", check=dep, message="dep not ready"))

    @app.route("/")
    async def index() -> str:  # pragma: no cover - not invoked by probes
        return "home"

    app.freeze()

    # Criterion 2a: /ready is 503 before startup completes (ready flag False).
    async with TestClient(app) as client:
        # __aenter__ flips ready True (mirrors lifespan). The async check still
        # fails, so /ready is 503 with the failure list.
        ready = await client.get("/ready")
        assert ready.status == 503
        assert "dep not ready" in ready.text

        # Criterion 1: /health is plain 200 regardless of checks.
        health = await client.get("/health")
        assert health.status == 200
        assert health.text == "ok"
        # Criterion 3: probe skips the secure stack — no Set-Cookie header.
        header_names = {k.lower() for k, _ in health.headers}
        assert "set-cookie" not in header_names

        # Criterion 2b: /ready turns 200 once the dependency check passes.
        failing["ok"] = True
        ready_ok = await client.get("/ready")
        assert ready_ok.status == 200
        assert ready_ok.text == "ready"

    # Criterion 2c: after the context exits (shutdown), ready resets to False.
    assert app._mutable_state.ready is False


async def _asgi_get(app: App, path: str) -> tuple[int, bytes]:
    """Drive one ASGI HTTP GET without running lifespan startup."""
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


@pytest.mark.issue(368)
async def test_ready_503_before_startup_flag_set() -> None:
    """A frozen-but-not-started app: ready flag False -> /ready is 503."""
    app = App(AppConfig(secret_key="x" * 32))
    app.freeze()
    assert app._mutable_state.ready is False  # never started
    status, body = await _asgi_get(app, "/ready")
    assert status == 503
    assert b"starting up" in body
    # /health is alive even before startup.
    health_status, health_body = await _asgi_get(app, "/health")
    assert health_status == 200
    assert health_body == b"ok"


@pytest.mark.issue(368)
async def test_probe_path_user_route_precedence() -> None:
    """A user route claiming a probe path wins; the probe steps aside."""
    app = App(AppConfig(secret_key="x" * 32, health_path="/health"))

    @app.route("/health")
    async def custom_health() -> str:
        return "custom health page"

    app.freeze()
    async with TestClient(app) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        assert resp.text == "custom health page"

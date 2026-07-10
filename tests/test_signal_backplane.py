"""Runtime proof for the private Redis signal backplane (#699)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import types
from typing import Any

import pytest

from chirp import App, AppConfig
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION
from chirp.errors import ConfigurationError
from chirp.pages.reactive.bus import ReactiveBus
from chirp.realtime.signal_backplane import (
    _SignalBackplaneCoordinator,
    _SignalBackplaneError,
    compile_signal_backplane_plan,
    signal_subject,
)
from chirp.realtime.signal_stream import make_signal_stream
from chirp.realtime.signals import SignalRegistry, SignalSpec


class _Broker:
    def __init__(self) -> None:
        self.subscribers: dict[
            str,
            set[
                tuple[
                    asyncio.Queue[dict[str, Any] | BaseException | None],
                    asyncio.AbstractEventLoop,
                ]
            ],
        ] = {}
        self.subscribed: list[tuple[str, ...]] = []
        self.published: list[tuple[str, bytes]] = []
        self.fail_publish = False
        self.fail_ping = False
        self.lock = threading.Lock()
        self.sync_clients: list[_SyncClient] = []
        self.pubsubs: list[_PubSub] = []

    def publish(self, subject: str, data: bytes) -> None:
        if self.fail_publish:
            raise ConnectionError("private redis details")
        message = {"type": "message", "channel": subject.encode(), "data": data}
        with self.lock:
            self.published.append((subject, data))
            subscribers = tuple(self.subscribers.get(subject, ()))
        for queue, loop in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, message)


class _SyncClient:
    def __init__(self, broker: _Broker) -> None:
        self.broker = broker
        self.closed = 0
        broker.sync_clients.append(self)

    def ping(self) -> bool:
        if self.broker.fail_ping:
            raise ConnectionError("private startup details")
        return True

    def publish(self, subject: str, data: bytes) -> None:
        self.broker.publish(subject, data)

    def close(self) -> None:
        self.closed += 1


class _PubSub:
    def __init__(self, broker: _Broker) -> None:
        self.broker = broker
        self.queue: asyncio.Queue[dict[str, Any] | BaseException | None] = asyncio.Queue()
        self.subjects: tuple[str, ...] = ()
        self.closed = False
        self.loop: asyncio.AbstractEventLoop | None = None
        broker.pubsubs.append(self)

    async def subscribe(self, *subjects: str) -> None:
        self.subjects = tuple(subjects)
        self.loop = asyncio.get_running_loop()
        with self.broker.lock:
            self.broker.subscribed.append(self.subjects)
            for subject in subjects:
                self.broker.subscribers.setdefault(subject, set()).add((self.queue, self.loop))

    async def listen(self):
        while True:
            message = await self.queue.get()
            if message is None:
                return
            if isinstance(message, BaseException):
                raise message
            yield message

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        loop = self.loop
        if loop is not None:
            with self.broker.lock:
                for subject in self.subjects:
                    self.broker.subscribers.get(subject, set()).discard((self.queue, loop))
            loop.call_soon_threadsafe(self.queue.put_nowait, None)

    def disconnect(self) -> None:
        loop = self.loop
        if loop is not None:
            loop.call_soon_threadsafe(
                self.queue.put_nowait, ConnectionError("private read details")
            )


class _AsyncClient:
    def __init__(self, broker: _Broker) -> None:
        self._pubsub = _PubSub(broker)
        self.closed = False

    def pubsub(self) -> _PubSub:
        return self._pubsub

    async def aclose(self) -> None:
        self.closed = True


class _RedisModule(types.ModuleType):
    __path__: list[str]
    from_url: Any
    asyncio: types.ModuleType


class _RedisAsyncModule(types.ModuleType):
    from_url: Any


def _patch_redis(monkeypatch: pytest.MonkeyPatch, broker: _Broker) -> None:
    redis_module = _RedisModule("redis")
    redis_module.__path__ = []
    async_module = _RedisAsyncModule("redis.asyncio")
    redis_module.from_url = lambda _url: _SyncClient(broker)
    async_module.from_url = lambda _url: _AsyncClient(broker)
    redis_module.asyncio = async_module
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", async_module)


def _plan():
    return compile_signal_backplane_plan(
        redis_url="redis://private.example/0", secret_key="shared-secret"
    )


async def _wait_subscribed(broker: _Broker, count: int = 1) -> None:
    for _ in range(100):
        with broker.lock:
            subscribed = len(broker.subscribed)
        if subscribed >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("fake Redis subscription did not become ready")


@pytest.mark.issue(699)
def test_subjects_are_stable_opaque_and_records_redact_sensitive_values() -> None:
    key = b"shared-secret"
    first = signal_subject(key, audience="session", audience_key="visitor-a", name="balance")
    second = signal_subject(key, audience="session", audience_key="visitor-a", name="balance")
    other = signal_subject(key, audience="session", audience_key="visitor-b", name="balance")
    assert first == second
    assert first != other
    assert "visitor-a" not in first
    assert "balance" not in first
    plan = _plan()
    coordinator = _SignalBackplaneCoordinator(plan, ReactiveBus())
    publication = coordinator.publication(
        name="balance",
        data="private payload",
        audience="session",
        audience_key="visitor-a",
    )
    rendered = repr(publication)
    assert "private payload" not in rendered
    assert publication.subject not in rendered
    assert "redis://" not in repr(plan)


@pytest.mark.issue(699)
def test_import_chirp_does_not_import_redis() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import chirp, sys; raise SystemExit('redis' in sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.issue(699)
async def test_missing_redis_extra_fails_with_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)
    coordinator = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    with pytest.raises(ConfigurationError, match=r"chirp\[redis\]"):
        await coordinator.start()
    await coordinator.close()
    await coordinator.close()


@pytest.mark.issue(699)
async def test_partial_startup_failure_closes_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    broker.fail_ping = True
    _patch_redis(monkeypatch, broker)
    coordinator = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    with pytest.raises(ConfigurationError, match="Could not start") as caught:
        await coordinator.start()
    assert "private startup details" not in str(caught.value)
    assert len(broker.sync_clients) == 1
    assert broker.sync_clients[0].closed == 1
    await coordinator.close()


@pytest.mark.issue(699)
async def test_two_coordinators_publish_rendered_html_over_exact_subjects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    publisher = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    subscriber = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await publisher.start()
    await subscriber.start()
    publication = publisher.publication(
        name="balance",
        data="<strong>42</strong>",
        audience="session",
        audience_key="visitor-a",
    )
    stream = subscriber.subscribe({publication.subject: "balance"})
    pending = asyncio.create_task(anext(stream))
    await _wait_subscribed(broker)
    publisher.publish(publication)
    update = await asyncio.wait_for(pending, timeout=1)
    assert (update.name, update.data) == ("balance", "<strong>42</strong>")
    assert broker.subscribed == [(publication.subject,)]
    assert broker.published == [(publication.subject, b"<strong>42</strong>")]
    await stream.aclose()
    await publisher.close()
    await publisher.close()
    await subscriber.close()


@pytest.mark.issue(699)
async def test_redis_subjects_isolate_two_session_audiences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    publisher = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    subscriber = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await publisher.start()
    await subscriber.start()
    alice = publisher.publication(
        name="balance", data="alice", audience="session", audience_key="visitor-a"
    )
    bob = publisher.publication(
        name="balance", data="bob", audience="session", audience_key="visitor-b"
    )
    alice_stream = subscriber.subscribe({alice.subject: "balance"})
    bob_stream = subscriber.subscribe({bob.subject: "balance"})
    alice_pending = asyncio.create_task(anext(alice_stream))
    bob_pending = asyncio.create_task(anext(bob_stream))
    await _wait_subscribed(broker, count=2)
    publisher.publish(alice)
    update = await asyncio.wait_for(alice_pending, timeout=1)
    assert update.data == "alice"
    await asyncio.sleep(0.02)
    assert not bob_pending.done()
    bob_pending.cancel()
    await asyncio.gather(bob_pending, return_exceptions=True)
    await alice_stream.aclose()
    await bob_stream.aclose()
    await publisher.close()
    await subscriber.close()


@pytest.mark.issue(699)
async def test_latest_slot_coalesces_per_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    publisher = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    subscriber = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await publisher.start()
    await subscriber.start()
    first = publisher.publication(name="status", data="old", audience="global", audience_key="")
    latest = publisher.publication(name="status", data="latest", audience="global", audience_key="")
    stream = subscriber.subscribe({first.subject: "status"})
    pending = asyncio.create_task(anext(stream))
    await _wait_subscribed(broker)
    publisher.publish(first)
    publisher.publish(latest)
    update = await asyncio.wait_for(pending, timeout=1)
    assert update.data == "latest"
    await stream.aclose()
    await publisher.close()
    await subscriber.close()


@pytest.mark.issue(699)
async def test_disconnect_requires_fresh_subscription_and_does_not_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    publisher = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    subscriber = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await publisher.start()
    await subscriber.start()
    publication = publisher.publication(
        name="status", data="during-gap", audience="global", audience_key=""
    )

    first_stream = subscriber.subscribe({publication.subject: "status"})
    first_pending = asyncio.create_task(anext(first_stream))
    await _wait_subscribed(broker)
    broker.pubsubs[-1].disconnect()
    with pytest.raises(_SignalBackplaneError, match="reconnect"):
        await asyncio.wait_for(first_pending, timeout=1)
    await first_stream.aclose()

    publisher.publish(publication)
    fresh_stream = subscriber.subscribe({publication.subject: "status"})
    fresh_pending = asyncio.create_task(anext(fresh_stream))
    await _wait_subscribed(broker, count=2)
    assert not fresh_pending.done(), "Redis Pub/Sub must not replay a gap publication"
    next_publication = publisher.publication(
        name="status", data="after-reconnect", audience="global", audience_key=""
    )
    publisher.publish(next_publication)
    update = await asyncio.wait_for(fresh_pending, timeout=1)
    assert update.data == "after-reconnect"
    await fresh_stream.aclose()
    await publisher.close()
    await subscriber.close()


@pytest.mark.issue(699)
async def test_shutdown_closes_active_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    coordinator = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await coordinator.start()
    subject = signal_subject(b"shared-secret", audience="global", audience_key="", name="status")
    stream = coordinator.subscribe({subject: "status"})
    pending = asyncio.create_task(anext(stream))
    await _wait_subscribed(broker)
    await coordinator.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, timeout=1)
    await stream.aclose()


@pytest.mark.issue(699)
async def test_publish_failure_is_visible_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    coordinator = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await coordinator.start()
    broker.fail_publish = True
    publication = coordinator.publication(
        name="balance",
        data="private payload",
        audience="session",
        audience_key="visitor-a",
    )
    with pytest.raises(_SignalBackplaneError) as caught:
        coordinator.publish(publication)
    message = str(caught.value)
    assert "balance" in message
    assert "private payload" not in message
    assert "visitor-a" not in message
    assert "redis://" not in message
    await coordinator.close()


@pytest.mark.issue(699)
async def test_free_threaded_publish_stress_and_close_are_fail_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    coordinator = _SignalBackplaneCoordinator(_plan(), ReactiveBus())
    await coordinator.start()
    publications = [
        coordinator.publication(
            name="status",
            data=str(index),
            audience="global",
            audience_key="",
        )
        for index in range(100)
    ]
    await asyncio.gather(
        *(asyncio.to_thread(coordinator.publish, publication) for publication in publications)
    )
    assert len(broker.published) == 100
    await coordinator.close()
    with pytest.raises(_SignalBackplaneError, match="closed"):
        coordinator.publish(publications[-1])


@pytest.mark.issue(699)
def test_distributed_append_emit_fails_actionably_before_publish() -> None:
    registry = SignalRegistry()
    registry.register(SignalSpec(name="audit", coalesce=False))
    registry.bind_backplane(_plan())
    with pytest.raises(_SignalBackplaneError, match="coalesce=False"):
        registry.emit("audit", "one")


@pytest.mark.issue(699)
def test_registry_repr_redacts_audience_keys_and_payloads() -> None:
    registry = SignalRegistry()
    registry.register(SignalSpec(name="balance", audience="session"))
    registry.seed("balance", "private payload", audience_key="visitor-a")
    rendered = repr(registry)
    assert "visitor-a" not in rendered
    assert "private payload" not in rendered


@pytest.mark.issue(699)
def test_render_failure_caches_raw_value_and_publishes_nothing(caplog) -> None:
    registry = SignalRegistry()

    def broken(_value: Any) -> str:
        raise RuntimeError("render exploded")

    registry.register(SignalSpec(name="status", render=broken))
    registry.emit("status", 42)
    assert registry.cached_value("status") == 42
    assert registry.cached_rendered("status") is None
    assert "status" in caplog.text


@pytest.mark.issue(699)
async def test_connection_owned_source_stays_local_in_redis_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    registry = SignalRegistry()

    async def source():
        yield 7
        await asyncio.sleep(1)

    registry.register(SignalSpec(name="ticks", source=source))
    registry.bind_backplane(_plan())
    await registry.start_backplane()
    stream = make_signal_stream(registry, ("ticks",)).generator.__aiter__()
    update = await asyncio.wait_for(anext(stream), timeout=1)
    assert (update.name, update.data) == ("ticks", "7")
    assert broker.published == []
    await stream.aclose()
    await registry.close_backplane()


@pytest.mark.issue(699)
async def test_remote_delivery_does_not_mutate_receiving_raw_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _Broker()
    _patch_redis(monkeypatch, broker)
    emitting = SignalRegistry()
    receiving = SignalRegistry()
    for registry in (emitting, receiving):
        registry.register(SignalSpec(name="balance", render=lambda value: f"${value}"))
        registry.bind_backplane(_plan())
        await registry.start_backplane()

    stream = make_signal_stream(receiving, ("balance",)).generator.__aiter__()
    pending = asyncio.create_task(anext(stream))
    await _wait_subscribed(broker)
    emitting.emit("balance", 42)
    update = await asyncio.wait_for(pending, timeout=1)
    assert update.data == "$42"
    assert receiving.cached_value("balance") is None
    await stream.aclose()
    await emitting.close_backplane()
    await receiving.close_backplane()


@pytest.mark.issue(699)
def test_production_server_uses_effective_worker_override() -> None:
    from chirp.server.production import run_production_server

    app = App(AppConfig(workers=1))

    @app.signal("status")
    async def status():
        if False:
            yield ""

    with pytest.raises(ConfigurationError) as caught:
        run_production_server(app, workers=2)
    assert str(caught.value) == (
        "Signals use a process-local bus with workers=2; realtime updates cannot "
        "reach clients connected to another worker.\n"
        "Set AppConfig(workers=1), or configure AppConfig(redis_url=...) / "
        "CHIRP_REDIS_URL for the private Redis signal backplane and keep signal "
        "source state in a shared store before deploying."
    )


@pytest.mark.issue(699)
@pytest.mark.parametrize(
    ("htmx_version", "headers", "expected_event", "expected_data"),
    [
        (None, {}, "event: balance", "data: <strong>42</strong>"),
        (
            HTMX4_PREVIEW_VERSION,
            {"HX-Request": "true", "HX-Request-Type": "partial"},
            None,
            "data: <hx-partial hx-target='[data-chirp-signal=\"balance\"]'>"
            "<strong>42</strong></hx-partial>",
        ),
    ],
)
async def test_round_robin_proxy_delivers_emit_across_instances(
    monkeypatch: pytest.MonkeyPatch,
    htmx_version: str | None,
    headers: dict[str, str],
    expected_event: str | None,
    expected_data: str,
) -> None:
    import httpx
    from pounce.testing import RoundRobinTestProxy, TestServer

    broker = _Broker()
    _patch_redis(monkeypatch, broker)

    def make_app() -> App:
        kwargs: dict[str, Any] = {
            "redis_url": "redis://private.example/0",
            "secret_key": "shared-secret",
        }
        if htmx_version is not None:
            kwargs.update(htmx=True, htmx_version=htmx_version)
        app = App(AppConfig(**kwargs))

        @app.signal("balance", render=lambda value: f"<strong>{value}</strong>")
        async def balance():
            if False:
                yield 0

        return app

    app_a = make_app()
    app_b = make_app()
    server_a = TestServer(app_a)
    server_b = TestServer(app_b)
    server_a.start()
    server_b.start()
    proxy = RoundRobinTestProxy((server_a, server_b))
    proxy.start()
    try:
        # Consume the first proxy connection so the SSE connection is pinned to B.
        async with httpx.AsyncClient(base_url=proxy.url, timeout=2) as primer:
            response = await primer.get("/health", headers={"Connection": "close"})
            assert response.status_code == 200

        async with httpx.AsyncClient(base_url=proxy.url, timeout=3) as client:
            request = client.build_request(
                "GET",
                "/_chirp/live?topics=balance",
                headers={"Accept": "text/event-stream", **headers},
            )
            response_task = asyncio.create_task(client.send(request, stream=True))
            await _wait_subscribed(broker)
            app_a.emit("balance", 42)
            response = await response_task
            assert response.status_code == 200
            lines: list[str] = []
            try:
                async for line in response.aiter_lines():
                    if line == "":
                        if any(item.startswith("data: ") for item in lines):
                            break
                        lines.clear()
                        continue
                    lines.append(line)
            finally:
                await response.aclose()
        if expected_event is None:
            assert not [line for line in lines if line.startswith("event: ")]
        else:
            assert expected_event in lines
        assert expected_data in lines
    finally:
        proxy.stop()
        server_b.stop()
        server_a.stop()

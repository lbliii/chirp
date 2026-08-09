"""Issue #950 — concurrent Suspense defers use separate Pelt pool checkouts.

Proves the checkout-isolation contract with today's ``Pool.acquire`` /
``Pool.release`` API and Suspense's concurrent defer drain (#948 DAG marks
independence; this file asserts pool ownership).
"""

from __future__ import annotations

import sys
import sysconfig
from typing import Any, cast

import anyio
import pytest
from kida import DictLoader, Environment

from chirp import Suspense
from chirp.data.drivers._pelt import _runtime
from chirp.data.drivers._pelt.pool import Pool
from chirp.templating.suspense import DEFERRED, plan_defer_execution, render_suspense

_INDEPENDENT_TEMPLATE = """\
<html><body>
<div id="a">{% block a %}{% if a is deferred %}<span class="sk">A</span>{% else %}<span>A:{{ a }}</span>{% end %}{% end %}</div>
<div id="b">{% block b %}{% if b is deferred %}<span class="sk">B</span>{% else %}<span>B:{{ b }}</span>{% end %}{% end %}</div>
<div id="c">{% block c %}{% if c is deferred %}<span class="sk">C</span>{% else %}<span>C:{{ c }}</span>{% end %}{% end %}</div>
<div id="d">{% block d %}{% if d is deferred %}<span class="sk">D</span>{% else %}<span>D:{{ d }}</span>{% end %}{% end %}</div>
</body></html>
"""

_COUPLED_TEMPLATE = """\
<html><body>
{% block panel %}
  {% if left is deferred %}
    <span class="sk">…</span>
  {% elif right is deferred %}
    <span class="sk">…</span>
  {% else %}
    <span>PANEL:{{ left }}|{{ right }}</span>
  {% end %}
{% end %}
</body></html>
"""


class _ProbeConnection:
    """Pool ownership probe — no PostgreSQL wire I/O."""

    def __init__(self, identifier: int) -> None:
        self.identifier = identifier
        self.reset_count = 0

    async def reset_if_needed(self) -> None:
        await anyio.sleep(0)
        self.reset_count += 1

    async def close(self) -> None:
        return None


def _nogil_runtime() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED")) and sys._is_gil_enabled() is False


def _env(template: str, name: str = "page.html") -> Environment:
    env = Environment(loader=DictLoader({name: template}))
    env.add_test("deferred", lambda val: val is DEFERRED)
    return env


async def _collect(env: Environment, suspense: Suspense) -> str:
    return "".join([chunk async for chunk in render_suspense(env, suspense, is_htmx=True)])


@pytest.mark.issue(950)
async def test_independent_suspense_defers_use_distinct_pelt_checkouts() -> None:
    """N independent defers ⇒ N distinct checkouts held concurrently."""
    n = 4
    probes = [_ProbeConnection(i) for i in range(n)]
    pool = Pool(cast(Any, probes))
    env = _env(_INDEPENDENT_TEMPLATE)
    plan = plan_defer_execution(env, "page.html", {"a", "b", "c", "d"})
    assert plan.independent_keys() == frozenset({"a", "b", "c", "d"})

    held: set[int] = set()
    peak_held = 0
    identities: dict[str, int] = {}
    lock = anyio.Lock()
    ready = anyio.Event()
    release = anyio.Event()

    async def load(key: str) -> str:
        nonlocal peak_held
        conn = cast(_ProbeConnection, await pool.acquire())
        try:
            async with lock:
                assert conn.identifier not in held, "connection borrowed by two defers"
                held.add(conn.identifier)
                identities[key] = conn.identifier
                peak_held = max(peak_held, len(held))
                if len(held) == n:
                    ready.set()
            await release.wait()
            return f"{key}-ok"
        finally:
            async with lock:
                held.discard(conn.identifier)
            await pool.release(cast(Any, conn))

    async def drive() -> str:
        suspense = Suspense(
            "page.html",
            a=load("a"),
            b=load("b"),
            c=load("c"),
            d=load("d"),
        )
        return await _collect(env, suspense)

    async with anyio.create_task_group() as tg:
        result_box: dict[str, str] = {}

        async def run_drive() -> None:
            result_box["body"] = await drive()

        tg.start_soon(run_drive)
        await ready.wait()
        assert peak_held == n
        assert len(set(identities.values())) == n
        assert held == set(range(n))
        release.set()

    body = result_box["body"]
    for key in ("a", "b", "c", "d"):
        assert f"{key.upper()}:{key}-ok" in body
    assert held == set()
    assert sum(p.reset_count for p in probes) == n
    # Every connection is available again for a fresh checkout.
    reacquired = [await pool.acquire() for _ in range(n)]
    assert {cast(_ProbeConnection, c).identifier for c in reacquired} == set(range(n))
    for conn in reacquired:
        await pool.release(cast(Any, conn))
    await pool.close()


@pytest.mark.issue(950)
async def test_serial_defers_return_connection_to_pool_between_checkouts() -> None:
    """A single-connection pool serves sequential defers without sharing across awaits."""
    probe = _ProbeConnection(0)
    pool = Pool([cast(Any, probe)])
    env = _env(
        """\
<html><body>
<div id="first">{% block first %}{% if first is deferred %}…{% else %}{{ first }}{% end %}{% end %}</div>
<div id="second">{% block second %}{% if second is deferred %}…{% else %}{{ second }}{% end %}{% end %}</div>
</body></html>
"""
    )

    phase = 0
    lock = anyio.Lock()
    first_released = anyio.Event()
    second_acquired = anyio.Event()

    async def load_first() -> str:
        nonlocal phase
        conn = await pool.acquire()
        try:
            async with lock:
                phase = 1
            await anyio.sleep(0.01)
            return "one"
        finally:
            await pool.release(conn)
            first_released.set()

    async def load_second() -> str:
        nonlocal phase
        await first_released.wait()
        conn = await pool.acquire()
        try:
            async with lock:
                phase = 2
            second_acquired.set()
            assert cast(_ProbeConnection, conn).identifier == 0
            return "two"
        finally:
            await pool.release(conn)

    # Force serial overlap: second waits until first has released so a size-1
    # pool proves republication rather than concurrent double-borrow.
    suspense = Suspense("page.html", first=load_first(), second=load_second())
    body = await _collect(env, suspense)
    assert "one" in body
    assert "two" in body
    assert phase == 2
    assert second_acquired.is_set()
    assert probe.reset_count == 2
    await pool.close()


@pytest.mark.issue(950)
async def test_coupled_defers_still_resolve_with_exclusive_checkouts() -> None:
    """Coupled keys still drain; each checkout remains exclusively owned."""
    probes = [_ProbeConnection(i) for i in range(2)]
    pool = Pool(cast(Any, probes))
    env = _env(_COUPLED_TEMPLATE, "coupled.html")
    plan = plan_defer_execution(env, "coupled.html", {"left", "right"})
    assert plan.coupled_key_pairs() == frozenset({("left", "right")})
    assert plan.independent_keys() == frozenset()

    held: set[int] = set()
    lock = anyio.Lock()
    ready = anyio.Event()
    release = anyio.Event()

    async def load(key: str) -> str:
        conn = cast(_ProbeConnection, await pool.acquire())
        try:
            async with lock:
                assert conn.identifier not in held
                held.add(conn.identifier)
                if len(held) == 2:
                    ready.set()
            await release.wait()
            return key
        finally:
            async with lock:
                held.discard(conn.identifier)
            await pool.release(cast(Any, conn))

    async with anyio.create_task_group() as tg:
        box: dict[str, str] = {}

        async def run() -> None:
            box["body"] = await _collect(
                env,
                Suspense("coupled.html", left=load("L"), right=load("R")),
            )

        tg.start_soon(run)
        await ready.wait()
        assert held == {0, 1}
        release.set()

    assert "PANEL:L|R" in box["body"]
    assert held == set()
    assert sum(p.reset_count for p in probes) == 2
    await pool.close()


@pytest.mark.issue(950)
async def test_pool_exhaustion_queues_acquire_without_sharing_connection() -> None:
    """When defers exceed pool size, excess awaits queue — they never share a conn.

    Failure mode: bounded wait on ``Pool.acquire()`` until a sibling releases.
    Size ``pool_size`` / ``PoolConfig.max_size`` to the peak concurrent
    independent Suspense checkouts you need, or accept queueing latency.
    """
    probes = [_ProbeConnection(i) for i in range(2)]
    pool = Pool(cast(Any, probes))
    env = _env(_INDEPENDENT_TEMPLATE)

    held: set[int] = set()
    peak_held = 0
    lock = anyio.Lock()
    two_held = anyio.Event()
    release_first_wave = anyio.Event()

    async def load(key: str) -> str:
        nonlocal peak_held
        conn = cast(_ProbeConnection, await pool.acquire())
        try:
            async with lock:
                assert conn.identifier not in held
                held.add(conn.identifier)
                peak_held = max(peak_held, len(held))
                if len(held) == 2:
                    two_held.set()
            # Hold until the first wave is allowed to release so the third
            # defer must wait on the semaphore rather than borrowing.
            await release_first_wave.wait()
            return key
        finally:
            async with lock:
                held.discard(conn.identifier)
            await pool.release(cast(Any, conn))

    async with anyio.create_task_group() as tg:
        box: dict[str, str] = {}

        async def run() -> None:
            box["body"] = await _collect(
                env,
                Suspense(
                    "page.html",
                    a=load("a"),
                    b=load("b"),
                    c=load("c"),
                    d="sync",  # keep template happy without a fourth checkout
                ),
            )

        tg.start_soon(run)
        await two_held.wait()
        assert peak_held == 2
        assert len(held) == 2
        # Third defer is blocked in acquire — not sharing either held identity.
        await anyio.sleep(0.05)
        assert len(held) == 2
        release_first_wave.set()

    body = box["body"]
    assert "a" in body
    assert "b" in body
    assert "c" in body
    assert peak_held == 2
    assert held == set()
    assert sum(p.reset_count for p in probes) == 3
    await pool.close()


@pytest.mark.issue(950)
@pytest.mark.skipif(
    not _nogil_runtime(),
    reason="requires a free-threaded build with PYTHON_GIL=0 (GIL disabled)",
)
async def test_independent_suspense_pelt_checkouts_under_nogil() -> None:
    """Same exclusive-checkout contract with the GIL disabled."""
    assert sys._is_gil_enabled() is False
    assert _runtime.is_free_threading_enabled() is True

    n = 3
    probes = [_ProbeConnection(i) for i in range(n)]
    pool = Pool(cast(Any, probes))
    env = _env(_INDEPENDENT_TEMPLATE)

    held: set[int] = set()
    peak_held = 0
    lock = anyio.Lock()
    ready = anyio.Event()
    release = anyio.Event()

    async def load(key: str) -> str:
        nonlocal peak_held
        conn = cast(_ProbeConnection, await pool.acquire())
        try:
            async with lock:
                assert conn.identifier not in held
                held.add(conn.identifier)
                peak_held = max(peak_held, len(held))
                if len(held) == n:
                    ready.set()
            await release.wait()
            return key
        finally:
            async with lock:
                held.discard(conn.identifier)
            await pool.release(cast(Any, conn))

    async with anyio.create_task_group() as tg:
        box: dict[str, str] = {}

        async def run() -> None:
            box["body"] = await _collect(
                env,
                Suspense(
                    "page.html",
                    a=load("a"),
                    b=load("b"),
                    c=load("c"),
                    d="sync",
                ),
            )

        tg.start_soon(run)
        await ready.wait()
        assert peak_held == n
        release.set()

    assert peak_held == n
    assert held == set()
    assert sys._is_gil_enabled() is False
    await pool.close()

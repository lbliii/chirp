"""Verify ContextVar isolation under concurrent async tasks.

Chirp relies on ContextVar for request-scoped state (request_var, g,
sessions, auth user, CSRF tokens). These tests verify that concurrent
tasks never see each other's context.
"""

import asyncio
from contextvars import ContextVar

from chirp.context import _RequestGlobals

# ---------------------------------------------------------------------------
# _RequestGlobals isolation
# ---------------------------------------------------------------------------


class TestRequestGlobalsIsolation:
    """g._store uses ContextVar — concurrent tasks should be isolated."""

    async def test_concurrent_tasks_see_own_g_values(self) -> None:
        """50 tasks each set g.task_id; none sees another's value."""
        g = _RequestGlobals()
        n_tasks = 50
        violations: list[str] = []
        lock = asyncio.Lock()

        async def task_fn(task_id: int) -> None:
            g.task_id = task_id
            g.data = f"data-{task_id}"
            # Yield to let other tasks run
            await asyncio.sleep(0.001)
            # Verify our values are still ours
            if g.task_id != task_id:
                async with lock:
                    violations.append(f"Task {task_id} saw g.task_id={g.task_id}")
            if g.data != f"data-{task_id}":
                async with lock:
                    violations.append(f"Task {task_id} saw g.data={g.data}")

        await asyncio.gather(*(task_fn(i) for i in range(n_tasks)))
        assert not violations, f"Context leaks: {violations}"

    async def test_g_reset_doesnt_affect_other_tasks(self) -> None:
        """Resetting g in one task doesn't clear another task's state."""
        g = _RequestGlobals()
        n_tasks = 20
        violations: list[str] = []
        lock = asyncio.Lock()

        async def setter(task_id: int) -> None:
            g.value = f"set-{task_id}"
            await asyncio.sleep(0.01)  # hold value while resetters run
            try:
                val = g.value
                if val != f"set-{task_id}":
                    async with lock:
                        violations.append(f"Setter {task_id} saw {val}")
            except AttributeError:
                async with lock:
                    violations.append(f"Setter {task_id}: g.value was reset!")

        async def resetter(task_id: int) -> None:
            g.value = f"temp-{task_id}"
            await asyncio.sleep(0.005)
            g._reset()

        tasks = []
        for i in range(n_tasks):
            tasks.append(asyncio.create_task(setter(i)))
            tasks.append(asyncio.create_task(resetter(i + 1000)))

        await asyncio.gather(*tasks)
        assert not violations, f"Context leaks after reset: {violations}"


# ---------------------------------------------------------------------------
# Raw ContextVar isolation
# ---------------------------------------------------------------------------


class TestContextVarIsolation:
    """Direct ContextVar isolation under asyncio.gather."""

    async def test_contextvar_per_task_isolation(self) -> None:
        """Each task gets its own ContextVar value via copy_context."""
        var: ContextVar[int] = ContextVar("test_var")
        n_tasks = 50
        violations: list[str] = []
        lock = asyncio.Lock()

        async def check_isolation(task_id: int) -> None:
            var.set(task_id)
            await asyncio.sleep(0.001)
            got = var.get()
            if got != task_id:
                async with lock:
                    violations.append(f"Task {task_id} saw {got}")

        await asyncio.gather(*(check_isolation(i) for i in range(n_tasks)))
        assert not violations, f"ContextVar leaks: {violations}"

    async def test_nested_tasks_inherit_parent_context(self) -> None:
        """Child tasks created via create_task inherit parent's ContextVar."""
        var: ContextVar[str] = ContextVar("parent_var")
        results: dict[int, str] = {}
        lock = asyncio.Lock()

        async def parent(pid: int) -> None:
            var.set(f"parent-{pid}")

            async def child() -> None:
                val = var.get()
                async with lock:
                    results[pid] = val

            await asyncio.create_task(child())

        await asyncio.gather(*(parent(i) for i in range(20)))

        for pid, val in results.items():
            assert val == f"parent-{pid}", f"Parent {pid}: child saw {val}"

"""Stress tests for Database connection pool under concurrent task access.

Uses SQLite in-memory to verify:
- 50 concurrent tasks can query without pool exhaustion
- Transactions serialize correctly under contention
- Connection is returned to pool after each operation
- No data corruption under concurrent INSERT/SELECT
"""

import asyncio
from dataclasses import dataclass

from chirp.data.database import Database


@dataclass(frozen=True, slots=True)
class Counter:
    id: int
    name: str
    value: int


class TestDatabasePoolStress:
    """Concurrent async tasks hitting the same SQLite database."""

    async def test_concurrent_reads_no_exhaustion(self) -> None:
        """50 tasks doing SELECT concurrently — all succeed."""
        async with Database("sqlite:///:memory:") as db:
            await db.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)"
            )
            for i in range(100):
                await db.execute("INSERT INTO items (name, value) VALUES (?, ?)", f"item-{i}", i)

            results: list[int] = []
            lock = asyncio.Lock()

            async def reader(task_id: int) -> None:
                rows = await db.fetch(Counter, "SELECT * FROM items WHERE value >= ?", task_id)
                async with lock:
                    results.append(len(rows))

            await asyncio.gather(*(reader(i) for i in range(50)))

            assert len(results) == 50
            # Each task should have gotten results (no errors, no empty due to pool issue)
            assert all(r >= 0 for r in results)
            # Task 0 should see all 100 rows, task 49 should see 51 rows
            assert results[0] == 100
            assert results[49] == 51

    async def test_concurrent_inserts_no_data_loss(self) -> None:
        """50 tasks each inserting 10 rows — all rows present at the end."""
        n_tasks = 50
        rows_per_task = 10

        async with Database("sqlite:///:memory:") as db:
            await db.execute(
                "CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_id INTEGER, seq INTEGER)"
            )

            async def inserter(task_id: int) -> None:
                for seq in range(rows_per_task):
                    await db.execute(
                        "INSERT INTO entries (task_id, seq) VALUES (?, ?)",
                        task_id,
                        seq,
                    )

            await asyncio.gather(*(inserter(i) for i in range(n_tasks)))

            count = await db.fetch_val("SELECT COUNT(*) FROM entries")
            assert count == n_tasks * rows_per_task

            # Verify each task's rows are all present
            for task_id in range(n_tasks):
                task_count = await db.fetch_val(
                    "SELECT COUNT(*) FROM entries WHERE task_id = ?", task_id
                )
                assert task_count == rows_per_task, (
                    f"Task {task_id}: expected {rows_per_task}, got {task_count}"
                )

    async def test_concurrent_transactions_serialize(self) -> None:
        """Concurrent transactions don't corrupt shared state."""
        async with Database("sqlite:///:memory:") as db:
            await db.execute("CREATE TABLE balance (id INTEGER PRIMARY KEY, amount INTEGER)")
            await db.execute("INSERT INTO balance (id, amount) VALUES (1, 1000)")

            n_tasks = 20
            increment = 10

            async def transactor(task_id: int) -> None:
                async with db.transaction():
                    current = await db.fetch_val("SELECT amount FROM balance WHERE id = 1")
                    await db.execute(
                        "UPDATE balance SET amount = ? WHERE id = 1",
                        current + increment,
                    )

            # SQLite serializes transactions via the async lock, so all
            # increments should be applied sequentially
            await asyncio.gather(*(transactor(i) for i in range(n_tasks)))

            final = await db.fetch_val("SELECT amount FROM balance WHERE id = 1")
            assert final == 1000 + (n_tasks * increment), (
                f"Expected {1000 + n_tasks * increment}, got {final}"
            )

    async def test_mixed_read_write_no_errors(self) -> None:
        """Concurrent readers and writers don't cause errors."""
        async with Database("sqlite:///:memory:") as db:
            await db.execute("CREATE TABLE log (id INTEGER PRIMARY KEY AUTOINCREMENT, msg TEXT)")

            errors: list[str] = []
            lock = asyncio.Lock()

            async def writer(task_id: int) -> None:
                try:
                    for i in range(20):
                        await db.execute("INSERT INTO log (msg) VALUES (?)", f"w{task_id}-{i}")
                except Exception as e:
                    async with lock:
                        errors.append(f"writer-{task_id}: {e}")

            async def reader(task_id: int) -> None:
                try:
                    for _ in range(20):
                        await db.fetch_val("SELECT COUNT(*) FROM log")
                except Exception as e:
                    async with lock:
                        errors.append(f"reader-{task_id}: {e}")

            tasks = [writer(i) for i in range(10)] + [reader(i) for i in range(10)]
            await asyncio.gather(*tasks)

            assert not errors, f"Errors during mixed access: {errors}"

            count = await db.fetch_val("SELECT COUNT(*) FROM log")
            assert count == 10 * 20  # 10 writers * 20 rows each

    async def test_pool_returns_to_baseline_after_burst(self) -> None:
        """After a burst of concurrent access, the pool is back to normal."""
        async with Database("sqlite:///:memory:") as db:
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")

            # Burst: 30 concurrent tasks
            async def burst_task(i: int) -> None:
                await db.execute("INSERT INTO t (v) VALUES (?)", f"burst-{i}")
                await db.fetch_val("SELECT COUNT(*) FROM t")

            await asyncio.gather(*(burst_task(i) for i in range(30)))

            # After burst, a single query should work fine
            count = await db.fetch_val("SELECT COUNT(*) FROM t")
            assert count == 30

            # Another burst should also work
            await asyncio.gather(*(burst_task(i + 100) for i in range(30)))
            count = await db.fetch_val("SELECT COUNT(*) FROM t")
            assert count == 60

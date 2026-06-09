"""Stress tests for Database connection pool under concurrent task access.

In-memory SQLite (single shared connection, serialized) verifies:
- 50 concurrent tasks can query without pool exhaustion
- Transactions serialize correctly under contention
- Connection is returned to pool after each operation
- No data corruption under concurrent INSERT/SELECT

File-backed SQLite (real WAL pool) verifies the #186 acceptance:
- Concurrent readers run in parallel (overlap timing), not serialized
- A long write transaction does not block concurrent reads
- Concurrent write transactions still serialize (no lost updates)
- The pool is sized by pool_size for files but collapses to one
  shared connection for in-memory databases
"""

import asyncio
from dataclasses import dataclass

import pytest

from chirp.data.database import Database
from chirp.data.errors import MigrationError
from chirp.data.migrate import migrate


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


class TestSqlitePoolConcurrency:
    """File-backed SQLite proves WAL concurrency: parallel readers, serialized writer.

    In-memory SQLite uses a single shared connection (serialized), so genuine
    concurrent-reader throughput is verified against a temp file with WAL.
    """

    async def test_concurrent_readers_run_in_parallel(self, tmp_path) -> None:
        """N slow readers overlap in time — they are not serialized.

        Each reader holds a connection while sleeping; if reads serialized on a
        single lock/connection, total wall time would be ~N * sleep. With a pool
        of WAL connections they overlap, so total time is far below the serial
        sum. This is the core acceptance: concurrent readers do not block.
        """
        url = f"sqlite:///{tmp_path / 'reads.db'}"
        n_readers = 5
        sleep = 0.2

        async with Database(url, pool_size=n_readers) as db:
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
            await db.execute("INSERT INTO t (v) VALUES (1)")

            async def slow_reader() -> None:
                # Acquire a pooled read connection, hold it across a sleep, then
                # read. If reads were serialized, these could not overlap.
                async with db._connection() as conn:
                    await asyncio.sleep(sleep)
                    cursor = await conn.execute("SELECT v FROM t")
                    await cursor.fetchone()

            start = asyncio.get_event_loop().time()
            await asyncio.gather(*(slow_reader() for _ in range(n_readers)))
            elapsed = asyncio.get_event_loop().time() - start

        # Serial would be ~n_readers * sleep (1.0s); parallel is ~sleep (0.2s).
        # Assert well below the serial floor to prove overlap without flakiness.
        assert elapsed < (n_readers * sleep) / 2, (
            f"Readers serialized: {elapsed:.3f}s for {n_readers} x {sleep}s sleeps"
        )

    async def test_long_write_txn_does_not_block_reads(self, tmp_path) -> None:
        """An open write transaction must not stall concurrent reads.

        A reader running while a slow write transaction is open should complete
        promptly (it does not wait for the write lock), proving the write lock no
        longer serializes the whole app.
        """
        url = f"sqlite:///{tmp_path / 'rw.db'}"

        async with Database(url, pool_size=4) as db:
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
            await db.execute("INSERT INTO t (v) VALUES (10)")

            read_done = asyncio.Event()

            async def slow_writer() -> None:
                async with db.transaction():
                    await db.execute("UPDATE t SET v = 20 WHERE id = 1")
                    # Hold the write transaction open; the reader should still
                    # complete during this window.
                    for _ in range(50):
                        if read_done.is_set():
                            break
                        await asyncio.sleep(0.01)

            async def reader() -> None:
                # Should return the last committed value (10) without waiting for
                # the writer to commit.
                val = await db.fetch_val("SELECT v FROM t WHERE id = 1")
                assert val == 10
                read_done.set()

            await asyncio.wait_for(
                asyncio.gather(slow_writer(), reader()),
                timeout=2.0,
            )
            assert read_done.is_set()
            # Writer committed afterward.
            assert await db.fetch_val("SELECT v FROM t WHERE id = 1") == 20

    async def test_concurrent_writers_serialize_correctly(self, tmp_path) -> None:
        """Concurrent write transactions still serialize — no lost updates."""
        url = f"sqlite:///{tmp_path / 'writers.db'}"
        n_tasks = 20
        increment = 10

        async with Database(url, pool_size=5) as db:
            await db.execute("CREATE TABLE balance (id INTEGER PRIMARY KEY, amount INTEGER)")
            await db.execute("INSERT INTO balance (id, amount) VALUES (1, 1000)")

            async def transactor() -> None:
                async with db.transaction():
                    current = await db.fetch_val("SELECT amount FROM balance WHERE id = 1")
                    await db.execute(
                        "UPDATE balance SET amount = ? WHERE id = 1", current + increment
                    )

            await asyncio.gather(*(transactor() for _ in range(n_tasks)))

            final = await db.fetch_val("SELECT amount FROM balance WHERE id = 1")
            assert final == 1000 + (n_tasks * increment)

    async def test_pool_sized_by_pool_size(self, tmp_path) -> None:
        """A file-backed pool opens pool_size connections, not one."""
        url = f"sqlite:///{tmp_path / 'sized.db'}"
        async with Database(url, pool_size=4) as db:
            await db.connect()
            assert db._pool.size == 4
            assert db._pool.is_memory is False

    async def test_memory_uses_single_shared_connection(self) -> None:
        """In-memory DB collapses to one shared connection visible to all tasks."""
        async with Database("sqlite:///:memory:", pool_size=5) as db:
            await db.connect()
            assert db._pool.size == 1
            assert db._pool.is_memory is True

            # A row written on the shared connection is visible to a later read.
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            await db.execute("INSERT INTO t (v) VALUES ('x')")
            assert await db.fetch_val("SELECT COUNT(*) FROM t") == 1

    async def test_cross_connection_read_your_writes(self, tmp_path) -> None:
        """A committed write on one pooled connection is visible on another (WAL).

        With a multi-connection pool a write may commit on connection A while a
        later read is served by connection B. WAL guarantees B observes A's
        committed write — this pins that safety property after splitting reads
        and writes across distinct pooled connections.
        """
        url = f"sqlite:///{tmp_path / 'ryw.db'}"
        async with Database(url, pool_size=4) as db:
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
            await db.execute("INSERT INTO t (v) VALUES (?)", 42)

            async def reader(expected: int) -> None:
                assert await db.fetch_val("SELECT v FROM t WHERE id = 1") == expected

            # Reads spread across pooled connections must all see the commit.
            await asyncio.gather(*(reader(42) for _ in range(12)))

            # An update committed on one connection is visible to later reads.
            await db.execute("UPDATE t SET v = ? WHERE id = 1", 99)
            await asyncio.gather(*(reader(99) for _ in range(12)))

    async def test_failed_migration_does_not_poison_pool(self, tmp_path) -> None:
        """End-to-end smoke: a failed migration leaves a clean, usable pool.

        Functional check that the migration error path is well-behaved (001
        committed, failed 002 rolled back, no connection left mid-transaction,
        pool still serves work). Note: in this single-task path the pool's LIFO
        acquire/release happens to hand the ROLLBACK back the same connection
        even without the fix, so this test does NOT by itself distinguish the
        pinned-connection remediation from the bug — that precise guard is
        ``test_failed_migration_pins_single_connection`` below.
        """
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        # 001 applies cleanly.
        (mig_dir / "001_ok.sql").write_text(
            "CREATE TABLE ok_table (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);"
        )
        # 002 fails mid-script: the CREATE succeeds inside the transaction, then
        # a statement against a missing table aborts it, leaving an open txn.
        (mig_dir / "002_bad.sql").write_text(
            "CREATE TABLE doomed (id INTEGER PRIMARY KEY);\n"
            "INSERT INTO does_not_exist (id) VALUES (1);"
        )
        url = f"sqlite:///{tmp_path / 'mig.db'}"
        async with Database(url, pool_size=3) as db:
            with pytest.raises(MigrationError):
                await migrate(db, mig_dir)

            # 001 committed; the failed 002 left nothing behind (rolled back).
            assert (
                await db.fetch_val(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ok_table'"
                )
                == 1
            )
            assert (
                await db.fetch_val(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='doomed'"
                )
                == 0
            )

            # No pooled connection is left mid-transaction — the failure rolled
            # back on the connection that opened it, not a different pooled one.
            for conn in db._pool._all:
                assert conn._conn.in_transaction is False

            # And the pool still accepts work: drive > pool_size concurrent
            # writes/reads; every insert must durably commit (a poisoned
            # connection would swallow its writes in an uncommitted txn).
            async def worker(i: int) -> None:
                await db.execute("INSERT INTO ok_table (name) VALUES (?)", f"w{i}")
                await db.fetch_val("SELECT COUNT(*) FROM ok_table")

            await asyncio.gather(*(worker(i) for i in range(10)))
            assert await db.fetch_val("SELECT COUNT(*) FROM ok_table") == 10

    async def test_failed_migration_pins_single_connection(self, tmp_path, monkeypatch) -> None:
        """A failed migration's script + ROLLBACK acquire exactly ONE connection.

        Precise regression guard for the rollback-on-wrong-connection bug,
        independent of pool acquire/release ordering. With the fix,
        ``_apply_migration`` wraps the script and its failure-path ROLLBACK in
        ``Database._pinned_connection()``, so the entire failing apply checks out
        exactly one pooled connection (both statements reuse it via
        ``_current_conn``). Without the pin, ``execute_script`` acquires+releases
        one connection and the separate ``ROLLBACK`` acquires a second — so an
        acquisition count of 1 (not 2) is what proves the connection is held
        across the failure, the property that prevents the ROLLBACK landing on a
        different connection under concurrency.
        """
        import chirp.data.drivers.sqlite as sqlite_driver
        from chirp.data.migrate import (
            Migration,
            _apply_migration,
            _ensure_tracking_table,
        )

        url = f"sqlite:///{tmp_path / 'pin.db'}"
        async with Database(url, pool_size=3) as db:
            await db.connect()
            await _ensure_tracking_table(db)

            # Count pooled-connection checkouts during the failing apply only.
            orig_acquire = sqlite_driver.SqlitePool.acquire
            acquisitions = 0

            async def counting_acquire(self):
                nonlocal acquisitions
                acquisitions += 1
                return await orig_acquire(self)

            monkeypatch.setattr(sqlite_driver.SqlitePool, "acquire", counting_acquire)

            # CREATE succeeds inside the txn, then the bad statement aborts it.
            bad = Migration(
                version=1,
                name="001_bad",
                sql="CREATE TABLE doomed (id INTEGER);\nINSERT INTO missing (id) VALUES (1);",
            )
            with pytest.raises(Exception):  # noqa: B017,PT011 — driver raises a wrapped error
                await _apply_migration(db, bad)

            assert acquisitions == 1, (
                f"failed migration acquired {acquisitions} pooled connections; the "
                "script and its ROLLBACK must share one pinned connection (>1 means "
                "the ROLLBACK could land on the wrong connection under contention)"
            )

            # And the connection that ran the failed script was rolled back, not
            # left mid-transaction.
            for conn in db._pool._all:
                assert conn._conn.in_transaction is False

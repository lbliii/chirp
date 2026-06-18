"""Tests for chirp.data — typed async database access."""

from dataclasses import dataclass

import pytest

from chirp.data import Database, DataError, Notification, get_db, migrate
from chirp.data._mapping import map_row, map_rows
from chirp.data.errors import MigrationError, QueryError

# -- Test models --


@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str


@dataclass(frozen=True, slots=True)
class Counter:
    total: int


# -- Fixtures --


@pytest.fixture
async def db(tmp_path):
    """Create a fresh SQLite database with a users table."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path}")
    await db.connect()
    await db.execute(
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  name TEXT NOT NULL,"
        "  email TEXT NOT NULL"
        ")"
    )
    yield db
    await db.disconnect()


@pytest.fixture
async def seeded_db(db):
    """Database with pre-seeded test data."""
    await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", "Alice", "alice@test.com")
    await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", "Bob", "bob@test.com")
    await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", "Carol", "carol@test.com")
    return db


# =============================================================================
# Driver detection
# =============================================================================


class TestDriverDetection:
    def test_sqlite_url(self) -> None:
        db = Database("sqlite:///test.db")
        assert db._driver == "sqlite"

    def test_sqlite_memory_url(self) -> None:
        db = Database("sqlite:///:memory:")
        assert db._driver == "sqlite"

    def test_postgresql_url(self) -> None:
        db = Database("postgresql://user:pass@localhost/db")
        assert db._driver == "postgresql"

    def test_postgres_url(self) -> None:
        db = Database("postgres://user:pass@localhost/db")
        assert db._driver == "postgresql"

    def test_unsupported_url_raises(self) -> None:
        with pytest.raises(DataError, match="Unsupported database URL scheme"):
            Database("mysql://localhost/db")


# =============================================================================
# Row-to-dataclass mapping
# =============================================================================


class TestMapping:
    def test_map_row_basic(self) -> None:
        row = {"id": 1, "name": "Alice", "email": "alice@test.com"}
        user = map_row(User, row)
        assert user == User(id=1, name="Alice", email="alice@test.com")

    def test_map_row_filters_extra_columns(self) -> None:
        row = {"id": 1, "name": "Alice", "email": "alice@test.com", "extra": "ignored"}
        user = map_row(User, row)
        assert user == User(id=1, name="Alice", email="alice@test.com")

    def test_map_row_raises_on_missing_field(self) -> None:
        row = {"id": 1, "name": "Alice"}  # missing email
        with pytest.raises(TypeError):
            map_row(User, row)

    def test_map_row_non_dataclass_raises(self) -> None:
        with pytest.raises(TypeError, match="not a dataclass"):
            map_row(dict, {"a": 1})  # type: ignore[arg-type]

    def test_map_row_non_dataclass_message_explains_fix(self) -> None:
        with pytest.raises(TypeError) as exc_info:
            map_row(dict, {"a": 1})  # type: ignore[arg-type]
        msg = str(exc_info.value)
        assert "frozen=True" in msg
        assert "slots=True" in msg
        assert "free-threaded" in msg

    def test_map_rows_non_dataclass_message_explains_fix(self) -> None:
        with pytest.raises(TypeError) as exc_info:
            map_rows(dict, [{"a": 1}])  # type: ignore[arg-type]
        msg = str(exc_info.value)
        assert "frozen=True" in msg
        assert "free-threaded" in msg

    def test_map_rows_basic(self) -> None:
        rows = [
            {"id": 1, "name": "Alice", "email": "a@b.com"},
            {"id": 2, "name": "Bob", "email": "b@b.com"},
        ]
        users = map_rows(User, rows)
        assert len(users) == 2
        assert users[0].name == "Alice"
        assert users[1].name == "Bob"

    def test_map_rows_empty(self) -> None:
        assert map_rows(User, []) == []


# =============================================================================
# Lifecycle
# =============================================================================


class TestLifecycle:
    async def test_connect_disconnect(self, tmp_path) -> None:
        db_path = tmp_path / "lifecycle.db"
        db = Database(f"sqlite:///{db_path}")
        assert not db._initialized
        await db.connect()
        assert db._initialized
        await db.disconnect()
        assert not db._initialized

    async def test_context_manager(self, tmp_path) -> None:
        db_path = tmp_path / "ctx.db"
        async with Database(f"sqlite:///{db_path}") as db:
            assert db._initialized
            await db.execute("CREATE TABLE t (id INTEGER)")
        assert not db._initialized

    async def test_lazy_connect_on_first_query(self, tmp_path) -> None:
        db_path = tmp_path / "lazy.db"
        db = Database(f"sqlite:///{db_path}")
        assert not db._initialized
        # First query triggers connect
        await db.execute("CREATE TABLE t (id INTEGER)")
        assert db._initialized
        await db.disconnect()

    async def test_double_connect_is_safe(self, db) -> None:
        await db.connect()  # already connected
        assert db._initialized

    async def test_double_disconnect_is_safe(self, tmp_path) -> None:
        db_path = tmp_path / "double.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()
        await db.disconnect()
        await db.disconnect()  # should not raise

    async def test_probe_returns_true_on_healthy_db(self, tmp_path) -> None:
        """probe() runs SELECT 1 on a fresh pooled connection and returns True."""
        db = Database(f"sqlite:///{tmp_path / 'probe.db'}")
        await db.connect()
        try:
            assert await db.probe() is True
        finally:
            await db.disconnect()

    async def test_probe_returns_false_on_failure(self, tmp_path, monkeypatch) -> None:
        """probe() never raises — a query/connection failure returns False."""
        import chirp.data.database as db_mod

        db = Database(f"sqlite:///{tmp_path / 'probe_fail.db'}")
        await db.connect()
        try:

            async def _boom(*args, **kwargs):
                raise RuntimeError("connection refused")

            monkeypatch.setattr(db_mod, "_execute_fetch_one", _boom)
            assert await db.probe() is False
        finally:
            await db.disconnect()


# =============================================================================
# Fetch
# =============================================================================


class TestFetch:
    async def test_fetch_all(self, seeded_db) -> None:
        users = await seeded_db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 3
        assert users[0].name == "Alice"
        assert users[1].name == "Bob"
        assert users[2].name == "Carol"

    async def test_fetch_with_params(self, seeded_db) -> None:
        users = await seeded_db.fetch(User, "SELECT * FROM users WHERE name = ?", "Alice")
        assert len(users) == 1
        assert users[0].email == "alice@test.com"

    async def test_fetch_empty(self, seeded_db) -> None:
        users = await seeded_db.fetch(User, "SELECT * FROM users WHERE name = ?", "Nobody")
        assert users == []

    async def test_fetch_one(self, seeded_db) -> None:
        user = await seeded_db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 1)
        assert user is not None
        assert user.name == "Alice"

    async def test_fetch_one_returns_none(self, seeded_db) -> None:
        user = await seeded_db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 999)
        assert user is None

    async def test_fetch_val(self, seeded_db) -> None:
        count = await seeded_db.fetch_val("SELECT COUNT(*) FROM users")
        assert count == 3

    async def test_fetch_val_with_type(self, seeded_db) -> None:
        count = await seeded_db.fetch_val("SELECT COUNT(*) FROM users", as_type=int)
        assert count == 3

    async def test_fetch_val_returns_none_on_empty(self, db) -> None:
        # Table exists but query returns no rows
        result = await db.fetch_val("SELECT name FROM users WHERE id = ?", 999)
        assert result is None


# =============================================================================
# Execute
# =============================================================================


class TestExecute:
    async def test_execute_insert(self, db) -> None:
        count = await db.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            "Dave",
            "dave@test.com",
        )
        assert count == 1

    async def test_execute_update(self, seeded_db) -> None:
        count = await seeded_db.execute(
            "UPDATE users SET email = ? WHERE name = ?",
            "new@test.com",
            "Alice",
        )
        assert count == 1
        user = await seeded_db.fetch_one(User, "SELECT * FROM users WHERE name = ?", "Alice")
        assert user is not None
        assert user.email == "new@test.com"

    async def test_execute_delete(self, seeded_db) -> None:
        count = await seeded_db.execute("DELETE FROM users WHERE name = ?", "Bob")
        assert count == 1
        remaining = await seeded_db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(remaining) == 2

    async def test_execute_many(self, db) -> None:
        count = await db.execute_many(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            [("Alice", "a@b.com"), ("Bob", "b@b.com"), ("Carol", "c@b.com")],
        )
        assert count == 3
        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 3

    async def test_execute_many_empty(self, db) -> None:
        count = await db.execute_many(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            [],
        )
        assert count == 0

    async def test_invalid_sql_raises_query_error(self, db) -> None:
        with pytest.raises(QueryError):
            await db.execute("INSERT INTO nonexistent (x) VALUES (?)", 1)


# =============================================================================
# Stream
# =============================================================================


class TestStream:
    async def test_stream_all_rows(self, seeded_db) -> None:
        rows = [user async for user in seeded_db.stream(User, "SELECT * FROM users ORDER BY id")]
        assert len(rows) == 3
        assert rows[0].name == "Alice"

    async def test_stream_with_params(self, seeded_db) -> None:
        rows = [
            user
            async for user in seeded_db.stream(User, "SELECT * FROM users WHERE name = ?", "Bob")
        ]
        assert len(rows) == 1
        assert rows[0].name == "Bob"

    async def test_stream_empty(self, seeded_db) -> None:
        rows = [
            user
            async for user in seeded_db.stream(User, "SELECT * FROM users WHERE name = ?", "Nobody")
        ]
        assert rows == []

    async def test_stream_small_batch(self, seeded_db) -> None:
        """Verify streaming works with batch_size smaller than result set."""
        rows = [
            user
            async for user in seeded_db.stream(
                User, "SELECT * FROM users ORDER BY id", batch_size=1
            )
        ]
        assert len(rows) == 3


# =============================================================================
# Transactions
# =============================================================================


class TestTransaction:
    async def test_transaction_commit(self, db) -> None:
        """Changes persist after a clean transaction exit."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice",
                "alice@test.com",
            )
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Bob",
                "bob@test.com",
            )

        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 2
        assert users[0].name == "Alice"
        assert users[1].name == "Bob"

    async def test_transaction_rollback(self, db) -> None:
        """Changes are reverted when an exception occurs."""
        # Seed one user outside the transaction
        await db.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            "Existing",
            "existing@test.com",
        )

        async def _insert_and_fail() -> None:
            async with db.transaction():
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "ShouldNotExist",
                    "gone@test.com",
                )
                msg = "deliberate"
                raise ValueError(msg)

        with pytest.raises(ValueError, match="deliberate"):
            await _insert_and_fail()

        # Only the pre-existing user should remain
        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 1
        assert users[0].name == "Existing"

    async def test_transaction_nested_is_transparent(self, db) -> None:
        """Nested transaction() joins the outer one."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice",
                "alice@test.com",
            )
            async with db.transaction():  # nested — no-op
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "Bob",
                    "bob@test.com",
                )

        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 2

    async def test_transaction_fetch_inside(self, db) -> None:
        """Reads inside a transaction see uncommitted writes."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice",
                "alice@test.com",
            )
            # Should see the uncommitted row
            count = await db.fetch_val("SELECT COUNT(*) FROM users")
            assert count == 1

    async def test_transaction_rollback_on_query_error(self, db) -> None:
        """Transaction rolls back if a QueryError occurs."""

        async def _insert_with_bad_query() -> None:
            async with db.transaction():
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "Alice",
                    "alice@test.com",
                )
                await db.execute("INSERT INTO nonexistent (x) VALUES (?)", 1)

        with pytest.raises(QueryError):
            await _insert_with_bad_query()

        # Nothing should be committed
        count = await db.fetch_val("SELECT COUNT(*) FROM users")
        assert count == 0


# =============================================================================
# Echo / query logging
# =============================================================================


class TestEcho:
    async def test_echo_logs_queries(self, tmp_path, caplog) -> None:
        import logging

        db_path = tmp_path / "echo.db"
        db = Database(f"sqlite:///{db_path}", echo=True)
        await db.connect()
        with caplog.at_level(logging.DEBUG, logger="chirp.data"):
            await db.execute("CREATE TABLE t (id INTEGER)")
            await db.execute("INSERT INTO t (id) VALUES (?)", 42)
        await db.disconnect()

        assert "CREATE TABLE" in caplog.text
        assert "INSERT INTO" in caplog.text

    async def test_no_echo_by_default(self, db, caplog) -> None:
        import logging

        with caplog.at_level(logging.DEBUG, logger="chirp.data"):
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice",
                "alice@test.com",
            )
        assert caplog.text == ""


# =============================================================================
# Migrations
# =============================================================================


class TestMigrations:
    async def test_migrate_applies_files(self, tmp_path) -> None:
        # Set up migration files
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_users.sql").write_text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        (migrations_dir / "002_add_email.sql").write_text("ALTER TABLE users ADD COLUMN email TEXT")

        db_path = tmp_path / "migrate.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        result = await migrate(db, migrations_dir)
        assert len(result.applied) == 2
        assert result.applied[0] == "001_create_users"
        assert result.applied[1] == "002_add_email"
        assert result.already_applied == 0
        assert result.total_available == 2

        # Verify tables were created
        await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", "Alice", "alice@test.com")
        count = await db.fetch_val("SELECT COUNT(*) FROM users")
        assert count == 1

        await db.disconnect()

    async def test_migrate_idempotent(self, tmp_path) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        db_path = tmp_path / "idem.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        # Run twice
        result1 = await migrate(db, migrations_dir)
        result2 = await migrate(db, migrations_dir)

        assert len(result1.applied) == 1
        assert len(result2.applied) == 0
        assert result2.already_applied == 1
        assert "up to date" in result2.summary

        await db.disconnect()

    async def test_migrate_incremental(self, tmp_path) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        db_path = tmp_path / "incr.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        # Apply first migration
        result1 = await migrate(db, migrations_dir)
        assert len(result1.applied) == 1

        # Add second migration
        (migrations_dir / "002_add_col.sql").write_text("ALTER TABLE t ADD COLUMN name TEXT")

        # Only the new one should apply
        result2 = await migrate(db, migrations_dir)
        assert len(result2.applied) == 1
        assert result2.applied[0] == "002_add_col"
        assert result2.already_applied == 1

        await db.disconnect()

    async def test_migrate_missing_directory_raises(self, tmp_path) -> None:
        db_path = tmp_path / "missing.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        with pytest.raises(MigrationError, match="does not exist"):
            await migrate(db, tmp_path / "nonexistent")

        await db.disconnect()

    async def test_migrate_empty_file_raises(self, tmp_path) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_empty.sql").write_text("")

        db_path = tmp_path / "empty.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        with pytest.raises(MigrationError, match="Empty migration"):
            await migrate(db, migrations_dir)

        await db.disconnect()

    async def test_migrate_failed_migration_rolls_back(self, tmp_path) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        (migrations_dir / "002_bad.sql").write_text("ALTER TABLE nonexistent ADD COLUMN x TEXT")

        db_path = tmp_path / "rollback.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        with pytest.raises(MigrationError, match="002_bad"):
            await migrate(db, migrations_dir)

        # First migration should still be applied (it succeeded)
        count = await db.fetch_val("SELECT COUNT(*) FROM _chirp_migrations")
        assert count == 1

        await db.disconnect()

    async def test_migrate_failed_multi_statement_does_not_leave_partial_table(
        self, tmp_path
    ) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_partial.sql").write_text(
            "CREATE TABLE leaked (id INTEGER PRIMARY KEY);\n"
            "ALTER TABLE missing_table ADD COLUMN x TEXT;"
        )

        db_path = tmp_path / "partial.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        with pytest.raises(MigrationError, match="001_partial"):
            await migrate(db, migrations_dir)

        table_count = await db.fetch_val(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='leaked'"
        )
        applied_count = await db.fetch_val("SELECT COUNT(*) FROM _chirp_migrations")
        assert table_count == 0
        assert applied_count == 0

        await db.disconnect()

    async def test_migrate_bad_filename_raises(self, tmp_path) -> None:
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "bad.sql").write_text("CREATE TABLE t (id INTEGER)")

        db_path = tmp_path / "bad.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        with pytest.raises(MigrationError, match="Invalid migration filename"):
            await migrate(db, migrations_dir)

        await db.disconnect()

    @pytest.mark.issue(367)
    async def test_migrate_edited_applied_migration_fails_loud(self, tmp_path) -> None:
        """Editing an already-applied migration file fails loud on the next run."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        mig = migrations_dir / "001_create_t.sql"
        mig.write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        db_path = tmp_path / "drift.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        result1 = await migrate(db, migrations_dir)
        assert result1.applied == ["001_create_t"]

        # Mutate the already-applied migration on disk.
        mig.write_text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

        with pytest.raises(MigrationError, match="001_create_t"):
            await migrate(db, migrations_dir)

        await db.disconnect()

    async def test_migrate_checksum_written_on_apply(self, tmp_path) -> None:
        """A fresh apply populates the checksum column."""
        import hashlib

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        sql = "CREATE TABLE t (id INTEGER PRIMARY KEY)"
        (migrations_dir / "001_create_t.sql").write_text(sql)

        db_path = tmp_path / "written.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        await migrate(db, migrations_dir)

        stored = await db.fetch_val("SELECT checksum FROM _chirp_migrations WHERE version = 1")
        # Migration.sql is the .strip()-ed file body.
        assert stored == hashlib.sha256(sql.encode("utf-8")).hexdigest()

        await db.disconnect()

    async def test_migrate_unchanged_reruns_clean(self, tmp_path) -> None:
        """Re-running with the file untouched is a no-op (no false drift)."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        db_path = tmp_path / "clean.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        await migrate(db, migrations_dir)
        result2 = await migrate(db, migrations_dir)
        assert result2.applied == []

        await db.disconnect()

    async def test_migrate_legacy_null_checksum_not_flagged(self, tmp_path) -> None:
        """A pre-checksum tracking row (NULL checksum) is never flagged as drift.

        Simulates a tracking table created by a pre-checksum Chirp version: the
        table has no checksum column, so the upgrade path adds it as NULL for the
        existing legacy row. Re-running migrate() must not raise.
        """
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_create_t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        db_path = tmp_path / "legacy.db"
        db = Database(f"sqlite:///{db_path}")
        await db.connect()

        # Hand-build the OLD (pre-checksum) tracking table + a legacy row, then
        # create the migration's table so the migration is "already applied".
        await db.execute(
            "CREATE TABLE _chirp_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        await db.execute(
            "INSERT INTO _chirp_migrations (version, name, applied_at) VALUES (1, ?, ?)",
            "001_create_t",
            "2026-01-01T00:00:00+00:00",
        )
        await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        # Upgrade path adds the column (NULL for the legacy row) and skips drift.
        result = await migrate(db, migrations_dir)
        assert result.applied == []

        legacy_checksum = await db.fetch_val(
            "SELECT checksum FROM _chirp_migrations WHERE version = 1"
        )
        assert legacy_checksum is None

        await db.disconnect()


# =============================================================================
# LISTEN/NOTIFY
# =============================================================================


class TestListen:
    async def test_listen_raises_on_sqlite(self, db) -> None:
        """LISTEN/NOTIFY is PostgreSQL-only — SQLite raises DataError."""
        with pytest.raises(DataError, match="PostgreSQL feature"):
            async for _ in db.listen("test_channel"):
                pass  # pragma: no cover

    def test_notification_dataclass(self) -> None:
        n = Notification(channel="orders", payload="42")
        assert n.channel == "orders"
        assert n.payload == "42"

    def test_notification_is_frozen(self) -> None:
        n = Notification(channel="orders", payload="42")
        with pytest.raises(AttributeError):
            n.channel = "other"  # type: ignore[misc]


# =============================================================================
# get_db() accessor
# =============================================================================


class TestGetDb:
    def test_get_db_raises_without_app(self) -> None:
        """get_db() raises LookupError when no App is running."""
        with pytest.raises(LookupError):
            get_db()

    async def test_get_db_returns_db_after_set(self, tmp_path) -> None:
        """get_db() returns the database after _db_var is set."""
        from chirp.data.database import _db_var

        db_path = tmp_path / "getdb.db"
        db = Database(f"sqlite:///{db_path}")
        token = _db_var.set(db)
        try:
            assert get_db() is db
        finally:
            _db_var.reset(token)


# =============================================================================
# App integration (db= and migrations= kwargs)
# =============================================================================


class TestAppIntegration:
    def test_app_db_raises_without_config(self) -> None:
        """app.db raises RuntimeError when no database is configured."""
        from chirp import App

        app = App()
        with pytest.raises(RuntimeError, match="No database configured"):
            _ = app.db

    def test_app_accepts_url_string(self) -> None:
        """App(db='sqlite:///...') creates a Database from the URL."""
        from chirp import App

        app = App(db="sqlite:///test.db")
        assert app.db._driver == "sqlite"

    def test_app_accepts_database_instance(self, tmp_path) -> None:
        """App(db=Database(...)) uses the passed instance."""
        from chirp import App

        db = Database(f"sqlite:///{tmp_path / 'inst.db'}")
        app = App(db=db)
        assert app.db is db

    def test_app_stores_migrations_dir(self) -> None:
        """App(migrations='...') stores the directory for startup."""
        from chirp import App

        app = App(db="sqlite:///test.db", migrations="migrations/")
        assert app._migrations_dir == "migrations/"


# =============================================================================
# Config and constructor
# =============================================================================


class TestDatabaseConfig:
    def test_default_pool_size(self) -> None:
        db = Database("sqlite:///test.db")
        assert db._config.pool_size == 5

    def test_custom_pool_size(self) -> None:
        db = Database("sqlite:///test.db", pool_size=20)
        assert db._config.pool_size == 20

    def test_echo_default_off(self) -> None:
        db = Database("sqlite:///test.db")
        assert db._config.echo is False

    def test_echo_enabled(self) -> None:
        db = Database("sqlite:///test.db", echo=True)
        assert db._config.echo is True


# =============================================================================
# Public API exports
# =============================================================================


class TestExports:
    def test_all_public_exports(self) -> None:
        """chirp.data.__all__ includes all public names."""
        import chirp.data

        expected = {
            "Composite",
            "Database",
            "DatabaseConnectionError",
            "DataError",
            "DriverNotInstalledError",
            "MigrationError",
            "NestedShape",
            "Notification",
            "PageResult",
            "Query",
            "QueryError",
            "Shape",
            "ShapeError",
            "composite",
            "get_db",
            "migrate",
            "nested",
            "register_shape",
            "shape",
            "shape_registry",
        }
        assert set(chirp.data.__all__) == expected

    def test_error_hierarchy(self) -> None:
        """All data errors inherit from DataError."""
        from chirp.data.errors import DatabaseConnectionError

        assert issubclass(QueryError, DataError)
        assert issubclass(MigrationError, DataError)
        assert issubclass(DatabaseConnectionError, DataError)

"""Tests for chirp.data — typed async database access."""

from dataclasses import dataclass

import pytest

from chirp.data import Database, DataError
from chirp.data._mapping import map_row, map_rows
from chirp.data.errors import DriverNotInstalledError, QueryError


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
        users = await seeded_db.fetch(
            User, "SELECT * FROM users WHERE name = ?", "Alice"
        )
        assert len(users) == 1
        assert users[0].email == "alice@test.com"

    async def test_fetch_empty(self, seeded_db) -> None:
        users = await seeded_db.fetch(
            User, "SELECT * FROM users WHERE name = ?", "Nobody"
        )
        assert users == []

    async def test_fetch_one(self, seeded_db) -> None:
        user = await seeded_db.fetch_one(
            User, "SELECT * FROM users WHERE id = ?", 1
        )
        assert user is not None
        assert user.name == "Alice"

    async def test_fetch_one_returns_none(self, seeded_db) -> None:
        user = await seeded_db.fetch_one(
            User, "SELECT * FROM users WHERE id = ?", 999
        )
        assert user is None

    async def test_fetch_val(self, seeded_db) -> None:
        count = await seeded_db.fetch_val("SELECT COUNT(*) FROM users")
        assert count == 3

    async def test_fetch_val_with_type(self, seeded_db) -> None:
        count = await seeded_db.fetch_val(
            "SELECT COUNT(*) FROM users", as_type=int
        )
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
            "Dave", "dave@test.com",
        )
        assert count == 1

    async def test_execute_update(self, seeded_db) -> None:
        count = await seeded_db.execute(
            "UPDATE users SET email = ? WHERE name = ?",
            "new@test.com", "Alice",
        )
        assert count == 1
        user = await seeded_db.fetch_one(
            User, "SELECT * FROM users WHERE name = ?", "Alice"
        )
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
        rows = []
        async for user in seeded_db.stream(User, "SELECT * FROM users ORDER BY id"):
            rows.append(user)
        assert len(rows) == 3
        assert rows[0].name == "Alice"

    async def test_stream_with_params(self, seeded_db) -> None:
        rows = []
        async for user in seeded_db.stream(
            User, "SELECT * FROM users WHERE name = ?", "Bob"
        ):
            rows.append(user)
        assert len(rows) == 1
        assert rows[0].name == "Bob"

    async def test_stream_empty(self, seeded_db) -> None:
        rows = []
        async for user in seeded_db.stream(
            User, "SELECT * FROM users WHERE name = ?", "Nobody"
        ):
            rows.append(user)
        assert rows == []

    async def test_stream_small_batch(self, seeded_db) -> None:
        """Verify streaming works with batch_size smaller than result set."""
        rows = []
        async for user in seeded_db.stream(
            User, "SELECT * FROM users ORDER BY id", batch_size=1
        ):
            rows.append(user)
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
                "Alice", "alice@test.com",
            )
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Bob", "bob@test.com",
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
            "Existing", "existing@test.com",
        )

        with pytest.raises(ValueError, match="deliberate"):
            async with db.transaction():
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "ShouldNotExist", "gone@test.com",
                )
                msg = "deliberate"
                raise ValueError(msg)

        # Only the pre-existing user should remain
        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 1
        assert users[0].name == "Existing"

    async def test_transaction_nested_is_transparent(self, db) -> None:
        """Nested transaction() joins the outer one."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice", "alice@test.com",
            )
            async with db.transaction():  # nested — no-op
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "Bob", "bob@test.com",
                )

        users = await db.fetch(User, "SELECT * FROM users ORDER BY id")
        assert len(users) == 2

    async def test_transaction_fetch_inside(self, db) -> None:
        """Reads inside a transaction see uncommitted writes."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice", "alice@test.com",
            )
            # Should see the uncommitted row
            count = await db.fetch_val("SELECT COUNT(*) FROM users")
            assert count == 1

    async def test_transaction_rollback_on_query_error(self, db) -> None:
        """Transaction rolls back if a QueryError occurs."""
        with pytest.raises(QueryError):
            async with db.transaction():
                await db.execute(
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    "Alice", "alice@test.com",
                )
                await db.execute("INSERT INTO nonexistent (x) VALUES (?)", 1)

        # Nothing should be committed
        count = await db.fetch_val("SELECT COUNT(*) FROM users")
        assert count == 0

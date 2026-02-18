"""Tests for chirp.data.Query — immutable query builder."""

from dataclasses import dataclass

import pytest

from chirp.data import Database, Query

# -- Test models --


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    text: str
    done: bool


@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str


# =============================================================================
# SQL compilation (no database needed)
# =============================================================================


class TestCompilation:
    """Test that Query builds the correct SQL and params."""

    def test_basic_select_all(self) -> None:
        q = Query(Todo, "todos")
        assert q.sql == "SELECT * FROM todos"
        assert q.params == ()

    def test_single_where(self) -> None:
        q = Query(Todo, "todos").where("done = ?", False)
        assert q.sql == "SELECT * FROM todos WHERE done = ?"
        assert q.params == (False,)

    def test_multiple_wheres_are_anded(self) -> None:
        q = Query(Todo, "todos").where("done = ?", False).where("id > ?", 10)
        assert q.sql == "SELECT * FROM todos WHERE done = ? AND id > ?"
        assert q.params == (False, 10)

    def test_where_with_multiple_params(self) -> None:
        q = Query(Todo, "todos").where("id BETWEEN ? AND ?", 5, 20)
        assert q.sql == "SELECT * FROM todos WHERE id BETWEEN ? AND ?"
        assert q.params == (5, 20)

    def test_order_by(self) -> None:
        q = Query(Todo, "todos").order_by("id DESC")
        assert q.sql == "SELECT * FROM todos ORDER BY id DESC"

    def test_take(self) -> None:
        q = Query(Todo, "todos").take(20)
        assert q.sql == "SELECT * FROM todos LIMIT 20"

    def test_skip(self) -> None:
        q = Query(Todo, "todos").skip(40)
        assert q.sql == "SELECT * FROM todos OFFSET 40"

    def test_select_columns(self) -> None:
        q = Query(Todo, "todos").select("id, text")
        assert q.sql == "SELECT id, text FROM todos"

    def test_full_chain(self) -> None:
        q = (
            Query(Todo, "todos")
            .select("id, text, done")
            .where("done = ?", False)
            .where("text LIKE ?", "%milk%")
            .order_by("id DESC")
            .take(20)
            .skip(40)
        )
        assert q.sql == (
            "SELECT id, text, done FROM todos "
            "WHERE done = ? AND text LIKE ? "
            "ORDER BY id DESC "
            "LIMIT 20 "
            "OFFSET 40"
        )
        assert q.params == (False, "%milk%")

    def test_order_by_replaces_previous(self) -> None:
        q = Query(Todo, "todos").order_by("id ASC").order_by("text DESC")
        assert q.sql == "SELECT * FROM todos ORDER BY text DESC"


# =============================================================================
# where_if (conditional clauses)
# =============================================================================


class TestWhereIf:
    """Test the conditional where clause builder."""

    def test_where_if_truthy_adds_clause(self) -> None:
        q = Query(Todo, "todos").where_if("active", "done = ?", False)
        assert q.sql == "SELECT * FROM todos WHERE done = ?"
        assert q.params == (False,)

    def test_where_if_falsy_skips_clause(self) -> None:
        q = Query(Todo, "todos").where_if("", "done = ?", False)
        assert q.sql == "SELECT * FROM todos"
        assert q.params == ()

    def test_where_if_none_skips_clause(self) -> None:
        q = Query(Todo, "todos").where_if(None, "done = ?", False)
        assert q.sql == "SELECT * FROM todos"
        assert q.params == ()

    def test_where_if_zero_skips_clause(self) -> None:
        q = Query(Todo, "todos").where_if(0, "id > ?", 0)
        assert q.sql == "SELECT * FROM todos"

    def test_where_if_mixed_truthy_and_falsy(self) -> None:
        search = "milk"
        status = ""
        q = (
            Query(Todo, "todos")
            .where_if(search, "text LIKE ?", f"%{search}%")
            .where_if(status, "done = ?", True)
        )
        assert q.sql == "SELECT * FROM todos WHERE text LIKE ?"
        assert q.params == ("%milk%",)

    def test_where_if_all_falsy_produces_no_where(self) -> None:
        q = (
            Query(Todo, "todos")
            .where_if(None, "done = ?", True)
            .where_if("", "text LIKE ?", "%x%")
            .where_if(0, "id > ?", 5)
        )
        assert q.sql == "SELECT * FROM todos"
        assert q.params == ()


# =============================================================================
# Immutability
# =============================================================================


class TestImmutability:
    """Ensure chaining returns new instances, never mutates the original."""

    def test_where_returns_new_instance(self) -> None:
        original = Query(Todo, "todos")
        filtered = original.where("done = ?", True)
        assert original is not filtered
        assert original.sql == "SELECT * FROM todos"
        assert "WHERE" in filtered.sql

    def test_order_by_returns_new_instance(self) -> None:
        original = Query(Todo, "todos")
        ordered = original.order_by("id")
        assert original is not ordered
        assert original._order is None
        assert ordered._order == "id"

    def test_take_returns_new_instance(self) -> None:
        original = Query(Todo, "todos")
        limited = original.take(10)
        assert original is not limited
        assert original._limit is None
        assert limited._limit == 10

    def test_skip_returns_new_instance(self) -> None:
        original = Query(Todo, "todos")
        offset = original.skip(20)
        assert original is not offset
        assert original._offset is None
        assert offset._offset == 20

    def test_select_returns_new_instance(self) -> None:
        original = Query(Todo, "todos")
        projected = original.select("id, text")
        assert original is not projected
        assert original._columns == "*"
        assert projected._columns == "id, text"

    def test_where_if_falsy_returns_same_instance(self) -> None:
        original = Query(Todo, "todos")
        same = original.where_if(None, "done = ?", True)
        assert original is same

    def test_branching_from_shared_base(self) -> None:
        """Two queries branch from the same base independently."""
        base = Query(Todo, "todos").where("done = ?", False)
        by_id = base.order_by("id")
        by_text = base.order_by("text")
        assert by_id._order == "id"
        assert by_text._order == "text"
        assert base._order is None


# =============================================================================
# Integration with Database (requires aiosqlite)
# =============================================================================


@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite database with a todos table."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path}")
    await db.connect()
    await db.execute(
        "CREATE TABLE todos ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  text TEXT NOT NULL,"
        "  done BOOLEAN NOT NULL DEFAULT 0"
        ")"
    )
    yield db
    await db.disconnect()


@pytest.fixture
async def seeded_db(db):
    """Database with pre-seeded todos."""
    await db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", "Buy milk", False)
    await db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", "Write tests", True)
    await db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", "Ship feature", False)
    await db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", "Buy eggs", False)
    await db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", "Deploy app", True)
    return db


class TestFetch:
    """Test query execution via fetch()."""

    async def test_fetch_all(self, seeded_db) -> None:
        todos = await Query(Todo, "todos").fetch(seeded_db)
        assert len(todos) == 5
        assert all(isinstance(t, Todo) for t in todos)

    async def test_fetch_with_where(self, seeded_db) -> None:
        todos = await Query(Todo, "todos").where("done = ?", False).fetch(seeded_db)
        assert len(todos) == 3
        assert all(not t.done for t in todos)

    async def test_fetch_with_order_and_limit(self, seeded_db) -> None:
        todos = await (
            Query(Todo, "todos")
            .order_by("id DESC")
            .take(2)
            .fetch(seeded_db)
        )
        assert len(todos) == 2
        assert todos[0].id > todos[1].id

    async def test_fetch_with_offset(self, seeded_db) -> None:
        all_todos = await Query(Todo, "todos").order_by("id").fetch(seeded_db)
        skipped = await (
            Query(Todo, "todos").order_by("id").take(100).skip(2).fetch(seeded_db)
        )
        assert skipped == all_todos[2:]

    async def test_fetch_empty_result(self, seeded_db) -> None:
        todos = await Query(Todo, "todos").where("id = ?", 9999).fetch(seeded_db)
        assert todos == []

    async def test_fetch_empty_table(self, db) -> None:
        todos = await Query(Todo, "todos").fetch(db)
        assert todos == []

    async def test_fetch_with_where_if_dynamic(self, seeded_db) -> None:
        """Simulate a dynamic filter endpoint."""
        search = "Buy"
        status = None
        todos = await (
            Query(Todo, "todos")
            .where_if(search, "text LIKE ?", f"%{search}%")
            .where_if(status, "done = ?", status)
            .order_by("id")
            .fetch(seeded_db)
        )
        assert len(todos) == 2
        assert todos[0].text == "Buy milk"
        assert todos[1].text == "Buy eggs"


class TestFetchOne:
    """Test query execution via fetch_one()."""

    async def test_fetch_one_returns_first_match(self, seeded_db) -> None:
        todo = await Query(Todo, "todos").order_by("id").fetch_one(seeded_db)
        assert todo is not None
        assert todo.id == 1

    async def test_fetch_one_with_where(self, seeded_db) -> None:
        todo = await Query(Todo, "todos").where("text = ?", "Buy milk").fetch_one(seeded_db)
        assert todo is not None
        assert todo.text == "Buy milk"
        assert not todo.done

    async def test_fetch_one_no_match_returns_none(self, seeded_db) -> None:
        todo = await Query(Todo, "todos").where("id = ?", 9999).fetch_one(seeded_db)
        assert todo is None


class TestCount:
    """Test query execution via count()."""

    async def test_count_all(self, seeded_db) -> None:
        n = await Query(Todo, "todos").count(seeded_db)
        assert n == 5

    async def test_count_with_where(self, seeded_db) -> None:
        n = await Query(Todo, "todos").where("done = ?", True).count(seeded_db)
        assert n == 2

    async def test_count_with_where_if(self, seeded_db) -> None:
        n = await (
            Query(Todo, "todos")
            .where_if("Buy", "text LIKE ?", "%Buy%")
            .count(seeded_db)
        )
        assert n == 2

    async def test_count_empty_table(self, db) -> None:
        n = await Query(Todo, "todos").count(db)
        assert n == 0

    async def test_count_ignores_limit_and_offset(self, seeded_db) -> None:
        """count() should count all matches, not just the limited set."""
        n = await Query(Todo, "todos").take(2).skip(1).count(seeded_db)
        assert n == 5


class TestExists:
    """Test query execution via exists()."""

    async def test_exists_when_rows_match(self, seeded_db) -> None:
        result = await Query(Todo, "todos").where("done = ?", True).exists(seeded_db)
        assert result is True

    async def test_exists_when_no_rows_match(self, seeded_db) -> None:
        result = await Query(Todo, "todos").where("id = ?", 9999).exists(seeded_db)
        assert result is False

    async def test_exists_empty_table(self, db) -> None:
        result = await Query(Todo, "todos").exists(db)
        assert result is False


class TestStream:
    """Test query execution via stream()."""

    async def test_stream_all(self, seeded_db) -> None:
        todos = [t async for t in Query(Todo, "todos").order_by("id").stream(seeded_db)]
        assert len(todos) == 5
        assert todos[0].id == 1

    async def test_stream_with_where(self, seeded_db) -> None:
        todos = [
            t async for t in Query(Todo, "todos").where("done = ?", False).stream(seeded_db)
        ]
        assert len(todos) == 3
        assert all(not t.done for t in todos)

    async def test_stream_empty_result(self, seeded_db) -> None:
        todos = [
            t async for t in Query(Todo, "todos").where("id = ?", 9999).stream(seeded_db)
        ]
        assert todos == []

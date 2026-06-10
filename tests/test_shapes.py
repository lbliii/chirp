"""Tests for chirp.data.shapes — the @shape Shape foundation (L1, #165).

L3 (#167/#169) adds the bounded nested compiler and tenant-scope coverage at the
bottom (``TestNestedCompiler`` / ``TestTenantScope``). L4 (#170/#171) adds the
page-composite + repository-seam coverage (``TestComposite`` /
``TestRepositorySeam``).
"""

import inspect
import threading
from dataclasses import dataclass

import pytest

from chirp.data import (
    Composite,
    Database,
    NestedShape,
    Shape,
    ShapeError,
    composite,
    nested,
    register_shape,
    shape,
    shape_registry,
)
from chirp.data.shapes import (
    _bind_params,
    _has_scope_predicate,
    _inject_scope,
    _scope_injectable,
    _ShapeMeta,
)

# -- Test models --


@shape("SELECT id, name FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class BoardView:
    id: int
    name: str


@shape("SELECT * FROM cards WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class BoardDetail:
    id: int
    title: str


# -- Fixtures --


@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite database with a boards table seeded with two rows."""
    db_path = tmp_path / "shapes.db"
    database = Database(f"sqlite:///{db_path}")
    await database.connect()
    await database.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    await database.execute("INSERT INTO boards (id, name) VALUES (?, ?)", 1, "Alpha")
    await database.execute("INSERT INTO boards (id, name) VALUES (?, ?)", 2, "Beta")
    yield database
    await database.disconnect()


# -- @shape validation --


class TestShapeValidation:
    def test_non_dataclass_raises(self) -> None:
        with pytest.raises(ShapeError, match="dataclass"):

            @shape("SELECT id FROM boards")
            class NotADataclass:
                pass

    def test_non_frozen_raises(self) -> None:
        with pytest.raises(ShapeError, match="frozen"):

            @shape("SELECT id FROM boards")
            @dataclass(slots=True)
            class Mutable:
                id: int

    def test_non_slots_raises(self) -> None:
        with pytest.raises(ShapeError, match="slot"):

            @shape("SELECT id FROM boards")
            @dataclass(frozen=True)
            class NoSlots:
                id: int

    def test_decorated_class_is_identity(self) -> None:
        """@shape returns the class unchanged — it is the row type."""
        assert isinstance(BoardView(id=1, name="x"), BoardView)

    def test_meta_attached(self) -> None:
        meta = BoardView.__chirp_shape__
        assert isinstance(meta, _ShapeMeta)
        assert meta.columns == ("id", "name")
        assert meta.name == "BoardView"
        assert meta.scope is None

    def test_frozen_instance(self) -> None:
        """Output rows are frozen — assignment raises."""
        row = BoardView(id=1, name="x")
        with pytest.raises((AttributeError, TypeError)):
            row.name = "y"  # type: ignore[misc]


# -- Accessors --


class TestAccessors:
    def test_sql(self) -> None:
        assert Shape.sql(BoardView) == "SELECT id, name FROM boards WHERE id = :id"

    def test_columns(self) -> None:
        assert Shape.columns(BoardView) == ("id", "name")

    def test_opaque_columns_empty(self) -> None:
        """SELECT * is opaque → columns=() (escape hatch, no false-positives)."""
        assert Shape.columns(BoardDetail) == ()

    def test_computed_default_empty(self) -> None:
        assert Shape.computed(BoardView) == frozenset()

    def test_computed_stored(self) -> None:
        @shape("SELECT id, name FROM boards", computed=("display_name",))
        @dataclass(frozen=True, slots=True)
        class BoardWithComputed:
            id: int
            name: str

        assert Shape.computed(BoardWithComputed) == frozenset({"display_name"})

    def test_accessor_on_non_shape_raises(self) -> None:
        @dataclass(frozen=True, slots=True)
        class Plain:
            id: int

        with pytest.raises(ShapeError, match="@shape"):
            Shape.sql(Plain)


# -- _bind_params --


class TestBindParams:
    def test_sqlite_single(self) -> None:
        sql, params = _bind_params("SELECT * FROM t WHERE id = :id", "sqlite", {"id": 7})
        assert sql == "SELECT * FROM t WHERE id = ?"
        assert params == (7,)

    def test_sqlite_multiple(self) -> None:
        sql, params = _bind_params(
            "SELECT * FROM t WHERE a = :a AND b = :b", "sqlite", {"a": 1, "b": 2}
        )
        assert sql == "SELECT * FROM t WHERE a = ? AND b = ?"
        assert params == (1, 2)

    def test_sqlite_repeated_name(self) -> None:
        """A repeated :name emits one ? per occurrence (positional)."""
        sql, params = _bind_params("SELECT * FROM t WHERE a = :x OR b = :x", "sqlite", {"x": 5})
        assert sql == "SELECT * FROM t WHERE a = ? OR b = ?"
        assert params == (5, 5)

    def test_postgres_single(self) -> None:
        sql, params = _bind_params("SELECT * FROM t WHERE id = :id", "postgresql", {"id": 7})
        assert sql == "SELECT * FROM t WHERE id = $1"
        assert params == (7,)

    def test_postgres_repeated_name_reuses_index(self) -> None:
        """A repeated :name reuses the same $N (one value per distinct name)."""
        sql, params = _bind_params("SELECT * FROM t WHERE a = :x OR b = :x", "postgresql", {"x": 5})
        assert sql == "SELECT * FROM t WHERE a = $1 OR b = $1"
        assert params == (5,)

    def test_postgres_cast_passthrough(self) -> None:
        """PostgreSQL ``::cast`` is not a placeholder."""
        sql, params = _bind_params("SELECT id::text FROM t WHERE id = :id", "postgresql", {"id": 1})
        assert sql == "SELECT id::text FROM t WHERE id = $1"
        assert params == (1,)

    def test_missing_param_raises(self) -> None:
        with pytest.raises(ShapeError, match=":id"):
            _bind_params("SELECT * FROM t WHERE id = :id", "sqlite", {})

    def test_params_never_concatenated(self) -> None:
        """A malicious value never lands in the SQL text — only in params."""
        sql, params = _bind_params(
            "SELECT * FROM t WHERE name = :name", "sqlite", {"name": "'; DROP TABLE t; --"}
        )
        assert "DROP TABLE" not in sql
        assert params == ("'; DROP TABLE t; --",)


# -- Execution against in-memory sqlite --


class TestExecution:
    async def test_fetch_returns_frozen_instances(self, db) -> None:
        rows = await Shape.fetch(BoardView, db, id=1)
        assert len(rows) == 1
        assert isinstance(rows[0], BoardView)
        assert rows[0].id == 1
        assert rows[0].name == "Alpha"
        with pytest.raises((AttributeError, TypeError)):
            rows[0].name = "mutated"  # type: ignore[misc]

    async def test_fetch_one(self, db) -> None:
        row = await Shape.fetch_one(BoardView, db, id=2)
        assert row is not None
        assert row.name == "Beta"

    async def test_fetch_one_none(self, db) -> None:
        row = await Shape.fetch_one(BoardView, db, id=999)
        assert row is None

    async def test_stream(self, db) -> None:
        @shape("SELECT id, name FROM boards WHERE id >= :min_id")
        @dataclass(frozen=True, slots=True)
        class StreamBoard:
            id: int
            name: str

        seen = [row async for row in Shape.stream(StreamBoard, db, min_id=1)]
        assert [r.id for r in seen] == [1, 2]
        assert all(isinstance(r, StreamBoard) for r in seen)

    async def test_name_binding_filters(self, db) -> None:
        """The :name placeholder actually parameterizes the query."""
        rows = await Shape.fetch(BoardView, db, id=2)
        assert [r.id for r in rows] == [2]


# -- Registry --


class TestRegistry:
    def test_auto_registered(self) -> None:
        reg = shape_registry()
        assert reg["BoardView"] is BoardView

    def test_registry_is_read_only(self) -> None:
        reg = shape_registry()
        with pytest.raises(TypeError):
            reg["x"] = object  # type: ignore[index]

    def test_registry_is_a_copy(self) -> None:
        """Mutating the live registry later is not reflected in an old snapshot view."""
        before = shape_registry()
        assert "AliasRoundTrip" not in before

        @shape("SELECT id FROM boards", name="AliasRoundTrip")
        @dataclass(frozen=True, slots=True)
        class AliasRoundTrip:
            id: int

        after = shape_registry()
        assert after["AliasRoundTrip"] is AliasRoundTrip
        # The earlier proxy reflects the live dict only if it were a view; it is a
        # frozen copy, so the new entry must be absent from it.
        assert "AliasRoundTrip" not in before

    def test_explicit_register_round_trip(self) -> None:
        @dataclass(frozen=True, slots=True)
        class Manual:
            id: int

        register_shape("ManualAlias", Manual)
        assert shape_registry()["ManualAlias"] is Manual

    def test_same_class_idempotent(self) -> None:
        @dataclass(frozen=True, slots=True)
        class Idem:
            id: int

        register_shape("IdemName", Idem)
        # Re-registering the same class under the same name is a no-op.
        register_shape("IdemName", Idem)
        assert shape_registry()["IdemName"] is Idem

    def test_different_class_collision_raises(self) -> None:
        @dataclass(frozen=True, slots=True)
        class First:
            id: int

        @dataclass(frozen=True, slots=True)
        class Second:
            id: int

        register_shape("CollideName", First)
        with pytest.raises(ShapeError, match="already registered"):
            register_shape("CollideName", Second)


# -- Concurrency --


class TestConcurrency:
    def test_concurrent_registration(self) -> None:
        """Many threads registering distinct shapes never lose entries or race."""

        @dataclass(frozen=True, slots=True)
        class Concurrent:
            id: int

        n = 64
        errors: list[BaseException] = []
        barrier = threading.Barrier(n)

        def worker(i: int) -> None:
            try:
                barrier.wait()
                register_shape(f"Concurrent_{i}", Concurrent)
            except BaseException as exc:  # collect for assertion
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        reg = shape_registry()
        for i in range(n):
            assert reg[f"Concurrent_{i}"] is Concurrent

    def test_concurrent_same_name_idempotent(self) -> None:
        """Many threads registering the SAME class under one name all succeed."""

        @dataclass(frozen=True, slots=True)
        class Shared:
            id: int

        n = 32
        errors: list[BaseException] = []
        barrier = threading.Barrier(n)

        def worker() -> None:
            try:
                barrier.wait()
                register_shape("SharedName", Shared)
            except BaseException as exc:  # collect for assertion
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert shape_registry()["SharedName"] is Shared


# ===========================================================================
# L3 (#167) — bounded nested compiler
# ===========================================================================
#
# Models form a depth-2 tree: Board -> Card -> Comment. Each child carries its
# join column (``board_id`` / ``card_id``) as a field so the compiler can group.


@shape("SELECT id, card_id, body FROM comments WHERE card_id = :card_id")
@dataclass(frozen=True, slots=True)
class NCComment:
    id: int
    card_id: int
    body: str


@shape("SELECT id, board_id, title FROM cards WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class NCCard:
    id: int
    board_id: int
    title: str
    comments: tuple[NCComment, ...] = nested(NCComment, on="card_id", key="id")


@shape("SELECT id, name FROM boards")
@dataclass(frozen=True, slots=True)
class NCBoard:
    id: int
    name: str
    cards: tuple[NCCard, ...] = nested(NCCard, on="board_id", key="id")


class _CountingDB:
    """Delegates to a real ``Database`` while counting ``fetch`` calls.

    The bounded-compiler guarantee is ``query_count == 1 + num_child_levels``
    regardless of parent row count, so the test counts the SELECT round trips.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self.fetch_count = 0

    @property
    def _driver(self) -> str:
        return self._db._driver

    async def fetch(self, cls, sql, /, *params):
        self.fetch_count += 1
        return await self._db.fetch(cls, sql, *params)

    async def fetch_one(self, cls, sql, /, *params):
        self.fetch_count += 1
        return await self._db.fetch_one(cls, sql, *params)


@pytest.fixture
async def nested_db(tmp_path):
    """SQLite DB with boards/cards/comments; row counts scale per test."""
    db_path = tmp_path / "nested.db"
    database = Database(f"sqlite:///{db_path}")
    await database.connect()
    await database.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    await database.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY, board_id INTEGER, title TEXT)"
    )
    await database.execute(
        "CREATE TABLE comments (id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT)"
    )
    yield database
    await database.disconnect()


async def _seed(database: Database, n_boards: int) -> None:
    """Seed n boards, 2 cards/board, 2 comments/card. ids are globally unique."""
    card_id = 0
    comment_id = 0
    for b in range(1, n_boards + 1):
        await database.execute("INSERT INTO boards (id, name) VALUES (?, ?)", b, f"Board {b}")
        for _ in range(2):
            card_id += 1
            await database.execute(
                "INSERT INTO cards (id, board_id, title) VALUES (?, ?, ?)",
                card_id,
                b,
                f"Card {card_id}",
            )
            for _ in range(2):
                comment_id += 1
                await database.execute(
                    "INSERT INTO comments (id, card_id, body) VALUES (?, ?, ?)",
                    comment_id,
                    card_id,
                    f"Comment {comment_id}",
                )


class TestNestedCompiler:
    def test_nested_field_descriptor(self) -> None:
        """nested() returns a field with an empty-tuple default + metadata."""
        meta = NCBoard.__chirp_shape__
        assert len(meta.nested) == 1
        ns = meta.nested[0]
        assert isinstance(ns, NestedShape)
        assert ns.cls is NCCard
        assert ns.field == "cards"
        assert ns.on == "board_id"
        assert ns.key == "id"

    def test_field_ordering_failloud(self) -> None:
        """A scalar field declared AFTER a nested() field -> ShapeError (§8.2 #2).

        Python accepts a scalar WITH a default after a default; @shape fails loud
        because it breaks the "nested fields last" compiler invariant.
        """
        with pytest.raises(ShapeError, match="after a nested"):

            @shape("SELECT id FROM boards WHERE id = :id")
            @dataclass(frozen=True, slots=True)
            class BadOrder:
                id: int
                kids: tuple = nested(NCComment, on="card_id", key="id")
                trailing: int = 0  # scalar after nested -> fail loud

    def test_plain_parent_row_maps_with_no_error(self, nested_db) -> None:
        """§8.2 #4: map_row coerces a @shape with a nested field with no error.

        The nested column is absent from the SQL row; the empty-tuple default
        fills it, and tuple[Child, ...] is non-coercible -> map_row is happy.
        """
        from chirp.data._mapping import map_row

        row = map_row(NCBoard, {"id": 1, "name": "Solo"})
        assert isinstance(row, NCBoard)
        assert row.cards == ()

    @pytest.mark.parametrize("n", [1, 30, 300])
    async def test_query_count_is_bounded(self, nested_db, n) -> None:
        """§8.2 #5(a): query_count == 1 + num_child_levels for any N (depth 2)."""
        await _seed(nested_db, n)
        counting = _CountingDB(nested_db)
        boards = await Shape.fetch(NCBoard, counting)  # type: ignore[arg-type]
        assert len(boards) == n
        # depth 2 => 1 parent + 1 card level + 1 comment level == 3, independent of N.
        assert counting.fetch_count == 3

    async def test_children_grouped_correctly(self, nested_db) -> None:
        """§8.2 #5(b): assembled child tuples land under the RIGHT parent."""
        await _seed(nested_db, 3)
        boards = await Shape.fetch(NCBoard, nested_db)
        by_id = {b.id: b for b in boards}
        # Each board has exactly its own 2 cards (board_id matches).
        for bid, board in by_id.items():
            assert len(board.cards) == 2
            assert all(c.board_id == bid for c in board.cards)
            # Each card has exactly its own 2 comments (card_id matches).
            for card in board.cards:
                assert len(card.comments) == 2
                assert all(cm.card_id == card.id for cm in card.comments)

    async def test_fetch_one_with_nested(self, nested_db) -> None:
        await _seed(nested_db, 2)
        board = await Shape.fetch_one(NCBoard, nested_db)
        assert board is not None
        # fetch_one returns the first parent with its children assembled.
        assert len(board.cards) == 2
        assert all(c.board_id == board.id for c in board.cards)

    async def test_stream_rejects_nested(self, nested_db) -> None:
        with pytest.raises(ShapeError, match="cannot be streamed"):
            async for _ in Shape.stream(NCBoard, nested_db):
                pass

    def test_validate_unexpressible_nested_raises(self) -> None:
        """A nested child with opaque SQL -> ShapeError at startup (§4-L3)."""

        @shape("SELECT * FROM widgets WHERE thing_id = :thing_id")
        @dataclass(frozen=True, slots=True)
        class OpaqueChild:
            id: int
            thing_id: int

        @shape("SELECT id, name FROM things WHERE id = :id")
        @dataclass(frozen=True, slots=True)
        class ParentWithOpaqueChild:
            id: int
            name: str
            kids: tuple[OpaqueChild, ...] = nested(OpaqueChild, on="thing_id", key="id")

        with pytest.raises(ShapeError, match=r"unexpressible|opaque"):
            Shape.validate(ParentWithOpaqueChild)

    def test_validate_missing_on_field_raises(self) -> None:
        """A child that does not carry its join column -> ShapeError at startup."""

        @shape("SELECT id, body FROM notes WHERE owner_id = :owner_id")
        @dataclass(frozen=True, slots=True)
        class NoteNoJoin:
            id: int
            body: str

        @shape("SELECT id FROM owners WHERE id = :id")
        @dataclass(frozen=True, slots=True)
        class OwnerWithBadChild:
            id: int
            notes: tuple[NoteNoJoin, ...] = nested(NoteNoJoin, on="owner_id", key="id")

        with pytest.raises(ShapeError, match="join column"):
            Shape.validate(OwnerWithBadChild)


# ===========================================================================
# L3 (#169) — tenant scope (structural injection on the compiler OUTPUT)
# ===========================================================================


class TestScopeInjection:
    def test_injects_into_existing_where(self) -> None:
        out = _inject_scope("SELECT id FROM t WHERE a = :a", "community_id")
        assert "community_id = :scope" in out
        assert "WHERE a = :a AND community_id = :scope" in out

    def test_injects_fresh_where_when_absent(self) -> None:
        out = _inject_scope("SELECT id FROM t", "community_id")
        assert out == "SELECT id FROM t WHERE community_id = :scope"

    def test_injects_before_order_by(self) -> None:
        out = _inject_scope("SELECT id FROM t WHERE a = :a ORDER BY id", "community_id")
        assert out == "SELECT id FROM t WHERE a = :a AND community_id = :scope ORDER BY id"

    def test_idempotent_when_already_scoped(self) -> None:
        sql = "SELECT id FROM t WHERE community_id = :scope"
        assert _inject_scope(sql, "community_id") == sql

    def test_opaque_select_star_not_injectable(self) -> None:
        assert not _scope_injectable("SELECT * FROM t WHERE a = :a")

    def test_cte_not_injectable(self) -> None:
        assert not _scope_injectable("WITH x AS (SELECT 1) SELECT id FROM x")

    def test_union_not_injectable(self) -> None:
        assert not _scope_injectable("SELECT id FROM a UNION SELECT id FROM b")

    def test_inject_raises_on_opaque(self) -> None:
        with pytest.raises(ShapeError, match="opaque"):
            _inject_scope("SELECT * FROM t", "community_id")

    def test_has_scope_predicate(self) -> None:
        assert _has_scope_predicate(
            "SELECT id FROM t WHERE t.community_id = :scope", "community_id"
        )
        assert not _has_scope_predicate("SELECT id FROM t WHERE a = :a", "community_id")


@shape(
    "SELECT id, board_id, title FROM scoped_cards WHERE board_id = :board_id", scope="community_id"
)
@dataclass(frozen=True, slots=True)
class ScopedCard:
    id: int
    board_id: int
    title: str


@shape("SELECT id, name FROM scoped_boards", scope="community_id")
@dataclass(frozen=True, slots=True)
class ScopedBoard:
    id: int
    name: str
    cards: tuple[ScopedCard, ...] = nested(ScopedCard, on="board_id", key="id")


class TestTenantScope:
    @pytest.fixture
    async def scope_db(self, tmp_path):
        db_path = tmp_path / "scope.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute(
            "CREATE TABLE scoped_boards (id INTEGER PRIMARY KEY, community_id INTEGER, name TEXT)"
        )
        await database.execute(
            "CREATE TABLE scoped_cards "
            "(id INTEGER PRIMARY KEY, board_id INTEGER, community_id INTEGER, title TEXT)"
        )
        # Tenant 1 owns board 1; tenant 2 owns board 2.
        await database.execute(
            "INSERT INTO scoped_boards (id, community_id, name) VALUES (1, 1, 'B1')"
        )
        await database.execute(
            "INSERT INTO scoped_boards (id, community_id, name) VALUES (2, 2, 'B2')"
        )
        # Board 1 (tenant 1) cards.
        await database.execute(
            "INSERT INTO scoped_cards (id, board_id, community_id, title) VALUES (10, 1, 1, 'C10')"
        )
        await database.execute(
            "INSERT INTO scoped_cards (id, board_id, community_id, title) VALUES (11, 1, 1, 'C11')"
        )
        # A cross-tenant card that joins to board 1 but belongs to tenant 2 ->
        # must be excluded by the scope predicate injected into the child query.
        await database.execute(
            "INSERT INTO scoped_cards (id, board_id, community_id, title) VALUES (12, 1, 2, 'LEAK')"
        )
        yield database
        await database.disconnect()

    async def test_scope_injected_into_parent_query(self) -> None:
        # The declared parent SQL has no scope predicate; the compiler injects it.
        assert not _has_scope_predicate(Shape.sql(ScopedBoard), "community_id")
        # validate() asserts the compiled OUTPUT carries the predicate (no raise).
        Shape.validate(ScopedBoard)

    async def test_scope_filters_parent_and_child(self, scope_db) -> None:
        boards = await Shape.fetch(ScopedBoard, scope_db, scope=1)
        # Tenant 1 sees only board 1 (board 2 belongs to tenant 2).
        assert [b.id for b in boards] == [1]
        board = boards[0]
        # The cross-tenant card (id=12, community_id=2) must be excluded by the
        # scope predicate injected into the child IN-list query.
        child_ids = sorted(c.id for c in board.cards)
        assert child_ids == [10, 11]
        assert 12 not in child_ids

    async def test_validate_passes_for_injectable_scoped_shape(self) -> None:
        # No raise for a plain injectable scoped shape.
        Shape.validate(ScopedCard)

    def test_validate_raises_for_opaque_scoped_shape(self) -> None:
        @shape("SELECT * FROM secrets WHERE id = :id", scope="community_id")
        @dataclass(frozen=True, slots=True)
        class OpaqueScoped:
            id: int

        with pytest.raises(ShapeError, match=r"opaque|cannot be structurally injected"):
            Shape.validate(OpaqueScoped)


# ===========================================================================
# L4 (#170) — page-composite + (#171) repository seam
# ===========================================================================
#
# A page declares its data ONCE: one @composite over @shape-decorated member
# fields (single-object and tuple). Composite.load runs the batched query set
# across the members and returns one frozen instance.


@shape("SELECT id, title FROM cp_boards WHERE id = :board_id")
@dataclass(frozen=True, slots=True)
class CPBoard:
    id: int
    title: str


@shape("SELECT id, name FROM cp_members WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class CPMember:
    id: int
    name: str


@shape("SELECT id, kind FROM cp_events WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class CPEvent:
    id: int
    kind: str


@composite()
@dataclass(frozen=True, slots=True)
class CPBoardPage:
    board: CPBoard  # single-object member -> fetch_one
    members: tuple[CPMember, ...]  # sequence member -> fetch
    activity: tuple[CPEvent, ...]


class _CountingDBC:
    """Real ``Database`` proxy that counts fetch/fetch_one round trips (#170)."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self.fetch_count = 0

    @property
    def _driver(self) -> str:
        return self._db._driver

    async def fetch(self, cls, sql, /, *params):
        self.fetch_count += 1
        return await self._db.fetch(cls, sql, *params)

    async def fetch_one(self, cls, sql, /, *params):
        self.fetch_count += 1
        return await self._db.fetch_one(cls, sql, *params)


@pytest.fixture
async def composite_db(tmp_path):
    db_path = tmp_path / "composite.db"
    database = Database(f"sqlite:///{db_path}")
    await database.connect()
    await database.execute("CREATE TABLE cp_boards (id INTEGER PRIMARY KEY, title TEXT)")
    await database.execute(
        "CREATE TABLE cp_members (id INTEGER PRIMARY KEY, board_id INTEGER, name TEXT)"
    )
    await database.execute(
        "CREATE TABLE cp_events (id INTEGER PRIMARY KEY, board_id INTEGER, kind TEXT)"
    )
    await database.execute("INSERT INTO cp_boards (id, title) VALUES (7, 'Roadmap')")
    await database.execute("INSERT INTO cp_members (id, board_id, name) VALUES (1, 7, 'Ada')")
    await database.execute("INSERT INTO cp_members (id, board_id, name) VALUES (2, 7, 'Lin')")
    await database.execute("INSERT INTO cp_events (id, board_id, kind) VALUES (1, 7, 'created')")
    yield database
    await database.disconnect()


class TestComposite:
    def test_meta_attached(self) -> None:
        meta = CPBoardPage.__chirp_composite__
        fields = {m.field: m for m in meta.members}
        assert set(fields) == {"board", "members", "activity"}
        assert fields["board"].shape_cls is CPBoard
        assert fields["board"].is_sequence is False
        assert fields["members"].shape_cls is CPMember
        assert fields["members"].is_sequence is True
        assert fields["activity"].shape_cls is CPEvent
        assert fields["activity"].is_sequence is True

    def test_non_shape_member_fails_loud(self) -> None:
        with pytest.raises(ShapeError, match="not a Shape member"):

            @composite()
            @dataclass(frozen=True, slots=True)
            class BadComposite:
                board: CPBoard
                count: int  # not a Shape -> fail loud

    def test_non_frozen_target_fails_loud(self) -> None:
        with pytest.raises(ShapeError, match="frozen"):

            @composite()
            @dataclass(slots=True)
            class Mutable:
                board: CPBoard

    async def test_load_not_a_composite_raises(self, composite_db) -> None:
        # Passing a plain @shape (not a @composite) to Composite.load fails loud.
        with pytest.raises(ShapeError, match="@composite"):
            await Composite.load(CPBoard, composite_db, board_id=7)  # type: ignore[arg-type]

    async def test_load_returns_one_frozen_instance(self, composite_db) -> None:
        page = await Composite.load(CPBoardPage, composite_db, board_id=7)
        assert isinstance(page, CPBoardPage)
        # The page is one frozen instance (#171 frozen-result assertion).
        with pytest.raises((AttributeError, TypeError)):
            page.board = None  # type: ignore[misc]
        assert isinstance(page.board, CPBoard)
        assert page.board.title == "Roadmap"
        assert isinstance(page.members, tuple)
        assert sorted(m.name for m in page.members) == ["Ada", "Lin"]
        assert isinstance(page.activity, tuple)
        assert [e.kind for e in page.activity] == ["created"]

    async def test_load_runs_one_query_per_member(self, composite_db) -> None:
        """The batched set is bounded: one query per member shape, not per block."""
        counting = _CountingDBC(composite_db)
        page = await Composite.load(CPBoardPage, counting, board_id=7)  # type: ignore[arg-type]
        # 3 members (board / members / activity) -> exactly 3 round trips.
        assert counting.fetch_count == 3
        assert page.board is not None

    async def test_single_member_absent_is_none(self, composite_db) -> None:
        page = await Composite.load(CPBoardPage, composite_db, board_id=999)
        # No board row for 999 -> single-object member is None; sequences empty.
        assert page.board is None
        assert page.members == ()
        assert page.activity == ()


# -- Tenant scope coalescing across composite members (#170 + #169) --


@shape("SELECT id, title FROM csc_boards WHERE id = :board_id", scope="community_id")
@dataclass(frozen=True, slots=True)
class CSCBoard:
    id: int
    title: str


@shape(
    "SELECT id, board_id, name FROM csc_members WHERE board_id = :board_id", scope="community_id"
)
@dataclass(frozen=True, slots=True)
class CSCMember:
    id: int
    board_id: int
    name: str


@composite(scope="community_id")
@dataclass(frozen=True, slots=True)
class CSCBoardPage:
    board: CSCBoard
    members: tuple[CSCMember, ...]


class TestCompositeScope:
    @pytest.fixture
    async def scoped_composite_db(self, tmp_path):
        db_path = tmp_path / "csc.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute(
            "CREATE TABLE csc_boards (id INTEGER PRIMARY KEY, community_id INTEGER, title TEXT)"
        )
        await database.execute(
            "CREATE TABLE csc_members "
            "(id INTEGER PRIMARY KEY, board_id INTEGER, community_id INTEGER, name TEXT)"
        )
        await database.execute(
            "INSERT INTO csc_boards (id, community_id, title) VALUES (7, 1, 'Owned')"
        )
        await database.execute(
            "INSERT INTO csc_members (id, board_id, community_id, name) VALUES (1, 7, 1, 'Ada')"
        )
        # A cross-tenant member that joins to board 7 but belongs to tenant 2 ->
        # must be excluded by the scope predicate threaded into the member query.
        await database.execute(
            "INSERT INTO csc_members (id, board_id, community_id, name) VALUES (2, 7, 2, 'LEAK')"
        )
        yield database
        await database.disconnect()

    async def test_scope_coalesced_to_members(self, scoped_composite_db) -> None:
        # The page declares scope once; Composite.load threads :scope to every
        # scoped member (both the board and the members query).
        page = await Composite.load(CSCBoardPage, scoped_composite_db, board_id=7, scope=1)
        assert page.board is not None
        assert page.board.title == "Owned"
        names = sorted(m.name for m in page.members)
        # The cross-tenant 'LEAK' member (community_id=2) is excluded.
        assert names == ["Ada"]


# -- Repository seam (#171): no render-time API takes a raw SQL string --


class TestRepositorySeam:
    def test_composite_load_returns_frozen(self) -> None:
        # Composite is a frozen, slotted dataclass model; the load result is one
        # frozen instance. (Behavioral round trip is covered above; this asserts
        # the declared model shape is frozen + slotted.)
        params = CPBoardPage.__dataclass_params__
        assert params.frozen is True
        assert getattr(CPBoardPage, "__slots__", None) is not None

    def test_no_public_render_time_api_takes_sql(self) -> None:
        # #171: SQL lives ONLY on @shape/@composite declarations and materializes
        # behind Shape.fetch / Composite.load (the Database facade). No public
        # render-time return type accepts a raw SQL string. Assert the render
        # return-type constructors expose no ``sql`` parameter.
        from chirp.templating import returns as _returns

        render_types = [
            getattr(_returns, n)
            for n in (
                "Template",
                "Fragment",
                "Page",
                "OOB",
                "Suspense",
                "Stream",
                "EventStream",
            )
            if hasattr(_returns, n)
        ]
        assert render_types  # sanity: we actually inspected some
        # Inspect parameter NAMES only -- never evaluate annotations (the module
        # uses ``from __future__ import annotations``, so a forward-referenced
        # annotation like ``PageComposition`` is unresolvable and irrelevant to
        # "is there a SQL parameter"). ``eval_str=False`` (the default) keeps
        # annotations as strings; on any other introspection failure we skip.
        inspected = 0
        for rt in render_types:
            try:
                sig = inspect.signature(rt)
            except TypeError, ValueError, NameError:
                # NameError: a forward-referenced annotation (e.g. PageComposition
                # in the OOB signature) is unresolvable; irrelevant to "is there a
                # SQL parameter". TypeError/ValueError: non-introspectable callable.
                continue
            inspected += 1
            assert "sql" not in sig.parameters, f"{rt.__name__} must not accept a SQL string"
        assert inspected  # at least one render type's signature was checkable

    def test_shape_and_composite_are_the_only_sql_surfaces(self) -> None:
        # The execution surfaces that carry SQL are Shape.* and Composite.load,
        # and they live in chirp.data (behind the Database facade) -- never as a
        # template-adjacent kwarg. Confirm the public load surface is a method on
        # Composite and returns by constructing the frozen model (not SQL).
        assert callable(Composite.load)
        # The composite declaration is where the page's data lives; loading it is
        # the repository boundary. No SQL string is reachable from the model.
        assert not any(
            isinstance(getattr(CPBoardPage, n, None), str) and "SELECT" in getattr(CPBoardPage, n)
            for n in dir(CPBoardPage)
        )

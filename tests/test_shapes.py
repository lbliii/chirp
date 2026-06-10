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
from chirp.data import shapes as _shapes_mod
from chirp.data.shapes import (
    _batched_child_sql,
    _bind_params,
    _decompose_child,
    _depth0_scope_predicate,
    _has_scope_predicate,
    _inject_scope,
    _member_params,
    _placeholder_names,
    _scan_placeholders,
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


# ===========================================================================
# SQL-compiler hardening (findings #4/#5/#6/#7/#8)
# ===========================================================================


# -- #8: one shared, quoted-string + cast aware placeholder scanner ----------


class TestDecomposeChild:
    def test_captures_order_by_and_limit(self) -> None:
        d = _decompose_child(
            "SELECT id, card_id, body FROM comments WHERE card_id = :card_id "
            "ORDER BY created_at DESC LIMIT 5",
            "card_id",
        )
        assert d.head == "SELECT id, card_id, body FROM comments"
        assert d.order_by == "created_at DESC"
        assert d.limit == "5"
        assert d.has_offset is False
        # Only the join equality was in the WHERE -> no residual filter.
        assert d.residual_where is None
        assert d.join_isolated is True

    def test_order_by_only(self) -> None:
        d = _decompose_child("SELECT id FROM t WHERE a = :a ORDER BY id", "a")
        assert d.order_by == "id"
        assert d.limit is None

    def test_offset_flagged(self) -> None:
        d = _decompose_child("SELECT id FROM t WHERE a = :a ORDER BY id LIMIT 2 OFFSET 5", "a")
        assert d.has_offset is True
        assert d.limit == "2"

    def test_subquery_order_by_left_on_head(self) -> None:
        """A depth>0 ORDER BY (inside an IN-subquery) is NOT the child's tail."""
        d = _decompose_child(
            "SELECT id FROM t WHERE id IN (SELECT y FROM u ORDER BY y) AND card_id = :card_id",
            "card_id",
        )
        # The only depth-0 boundary is the WHERE; the subquery ORDER BY stays in head.
        assert d.head == "SELECT id FROM t"
        assert d.order_by is None
        assert d.limit is None
        # The residual is the leading IN-subquery predicate; the join equality
        # (``card_id = :card_id``) is isolated and dropped from the residual.
        assert d.join_isolated is True
        assert d.residual_where == "id IN (SELECT y FROM u ORDER BY y)"

    def test_residual_where_preserved(self) -> None:
        """A non-join WHERE filter survives the IN-list rewrite (finding A3)."""
        d = _decompose_child(
            "SELECT id, card_id, body FROM comments WHERE card_id = :card_id AND deleted = 0",
            "card_id",
        )
        assert d.head == "SELECT id, card_id, body FROM comments"
        assert d.join_isolated is True
        assert d.residual_where == "deleted = 0"

    def test_join_predicate_ord_at_top_level_not_isolated(self) -> None:
        """An OR'd join predicate cannot be safely isolated (finding A3)."""
        d = _decompose_child(
            "SELECT id, card_id FROM c WHERE card_id = :card_id OR x = 1", "card_id"
        )
        assert d.join_isolated is False

    def test_non_equality_join_predicate_not_isolated(self) -> None:
        d = _decompose_child("SELECT id, card_id FROM c WHERE card_id > :card_id", "card_id")
        assert d.join_isolated is False

    def test_absent_join_predicate_not_isolated(self) -> None:
        d = _decompose_child("SELECT id, card_id FROM c WHERE deleted = 0", "card_id")
        assert d.join_isolated is False

    def test_no_where_is_vacuously_isolated(self) -> None:
        d = _decompose_child("SELECT id, card_id FROM c", "card_id")
        assert d.join_isolated is True
        assert d.residual_where is None


class TestSharedPlaceholderScanner:
    def test_scan_skips_colon_in_string_literal(self) -> None:
        """A ``:name``-shaped token inside a string literal is NOT a placeholder."""
        names = [n for n, _, _ in _scan_placeholders("SELECT '12:30:00' AS t, id FROM x")]
        assert names == []
        names = _placeholder_names("SELECT '12:30:00' AS t FROM x WHERE id = :id")
        assert names == {"id"}

    def test_scan_skips_cast(self) -> None:
        names = _placeholder_names("SELECT id::text FROM t WHERE id = :id")
        assert names == {"id"}

    def test_scan_double_quote_string(self) -> None:
        """A colon inside a double-quoted string is not a placeholder either."""
        names = _placeholder_names('SELECT "a:b" FROM t WHERE id = :id')
        assert names == {"id"}

    def test_scan_doubled_quote_escape(self) -> None:
        """A doubled-quote escape ('') keeps the scanner inside the string."""
        names = _placeholder_names("SELECT 'it''s :30' AS t FROM x WHERE id = :id")
        assert names == {"id"}

    def test_bind_params_string_literal_not_a_placeholder(self) -> None:
        """_bind_params must not treat a colon inside a literal as a placeholder."""
        sql, params = _bind_params(
            "SELECT * FROM t WHERE label = '12:00' AND id = :id", "sqlite", {"id": 7}
        )
        # The literal is untouched; only :id is rewritten to ?.
        assert sql == "SELECT * FROM t WHERE label = '12:00' AND id = ?"
        assert params == (7,)

    def test_bind_and_names_agree(self) -> None:
        """The two callers agree because they share one scanner."""
        sql = "SELECT '::not a cast', id FROM t WHERE a = :a AND b = :b AND c = :a"
        names = _placeholder_names(sql)
        bound, params = _bind_params(sql, "postgresql", {"a": 1, "b": 2})
        assert names == {"a", "b"}
        # PG reuses $1 for the repeated :a (one value per distinct name).
        assert bound.count("$1") == 2
        assert params == (1, 2)


# -- #6: derived-table / subquery scope-injection rejection (fail loud) ------


class TestDerivedTableScopeRejection:
    def test_from_subquery_not_injectable(self) -> None:
        sql = "SELECT id FROM (SELECT id FROM t WHERE a = 1) x WHERE x.id = :id"
        assert not _scope_injectable(sql)

    def test_scalar_subquery_projection_not_injectable(self) -> None:
        sql = "SELECT id, (SELECT count(*) FROM u) AS n FROM t WHERE id = :id"
        assert not _scope_injectable(sql)

    def test_in_subquery_in_where_is_injectable(self) -> None:
        """A subquery in the WHERE (after the depth-0 WHERE) stays injectable."""
        sql = "SELECT id FROM t WHERE id IN (SELECT y FROM u WHERE z = 1)"
        assert _scope_injectable(sql)

    def test_inject_into_in_subquery_query_targets_outer_where(self) -> None:
        """Scope lands in the OUTER WHERE, not inside the IN-subquery."""
        out = _inject_scope(
            "SELECT id FROM t WHERE id IN (SELECT y FROM u WHERE z = 1) ORDER BY id",
            "community_id",
        )
        # The predicate is appended to the outer query, before the outer ORDER BY,
        # and the inner subquery's ORDER-less WHERE is untouched.
        assert out == (
            "SELECT id FROM t WHERE id IN (SELECT y FROM u WHERE z = 1) "
            "AND community_id = :scope ORDER BY id"
        )

    def test_inject_raises_on_from_subquery(self) -> None:
        with pytest.raises(ShapeError, match=r"opaque|derived"):
            _inject_scope(
                "SELECT id FROM (SELECT id FROM t WHERE a = 1) x WHERE x.id = :id",
                "community_id",
            )

    def test_validate_rejects_scoped_from_subquery_shape(self) -> None:
        @shape(
            "SELECT id, board_id FROM (SELECT id, board_id FROM raw WHERE ok = 1) x "
            "WHERE x.board_id = :board_id",
            scope="community_id",
        )
        @dataclass(frozen=True, slots=True)
        class DerivedScoped:
            id: int
            board_id: int

        with pytest.raises(ShapeError, match=r"opaque|derived|cannot be"):
            Shape.validate(DerivedScoped)


# -- #7: scope idempotency + author-predicate fail-loud ----------------------


class TestScopeAuthorPredicate:
    def test_idempotent_canonical_form(self) -> None:
        sql = "SELECT id FROM t WHERE community_id = :scope"
        assert _inject_scope(sql, "community_id") == sql

    def test_idempotent_canonical_with_table_qualifier(self) -> None:
        sql = "SELECT id FROM t WHERE t.community_id = :scope"
        assert _inject_scope(sql, "community_id") == sql

    def test_author_predicate_different_placeholder_fails_loud(self) -> None:
        """An author-written scope predicate with a non-canonical RHS fails loud."""
        with pytest.raises(ShapeError, match=r"author-written|owned by the compiler"):
            _inject_scope("SELECT id FROM t WHERE community_id = :tenant", "community_id")

    def test_author_predicate_in_list_fails_loud(self) -> None:
        with pytest.raises(ShapeError, match=r"author-written|owned by the compiler"):
            _inject_scope("SELECT id FROM t WHERE community_id IN (1, 2)", "community_id")

    def test_has_scope_predicate_is_depth_aware(self) -> None:
        """A scope predicate inside a subquery does not fool the backstop."""
        # The only scope predicate is at depth>0 (inside the IN-subquery) -> the
        # outer query is NOT considered already-scoped.
        sql = "SELECT id FROM t WHERE id IN (SELECT y FROM u WHERE community_id = :scope)"
        assert not _has_scope_predicate(sql, "community_id")

    def test_no_double_injection(self) -> None:
        """The canonical predicate is injected exactly once (idempotent re-run)."""
        once = _inject_scope("SELECT id FROM t WHERE a = :a", "community_id")
        twice = _inject_scope(once, "community_id")
        assert once == twice
        assert once.count("community_id = :scope") == 1


# -- #4: ordered / limited child correctness (re-attach + window top-N) -------


@shape(
    "SELECT id, card_id, body FROM oc_comments WHERE card_id = :card_id ORDER BY id DESC LIMIT 2"
)
@dataclass(frozen=True, slots=True)
class OCComment:
    id: int
    card_id: int
    body: str


@shape("SELECT id, name FROM oc_cards")
@dataclass(frozen=True, slots=True)
class OCCard:
    id: int
    name: str
    comments: tuple[OCComment, ...] = nested(OCComment, on="card_id", key="id")


@shape("SELECT id, card_id, body FROM oo_comments WHERE card_id = :card_id ORDER BY id ASC")
@dataclass(frozen=True, slots=True)
class OOComment:
    id: int
    card_id: int
    body: str


@shape("SELECT id, name FROM oc_cards")
@dataclass(frozen=True, slots=True)
class OOCard:
    id: int
    name: str
    comments: tuple[OOComment, ...] = nested(OOComment, on="card_id", key="id")


class TestOrderedLimitedChild:
    @pytest.fixture
    async def ordered_db(self, tmp_path):
        db_path = tmp_path / "ordered.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE oc_cards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE oc_comments (id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT)"
        )
        await database.execute(
            "CREATE TABLE oo_comments (id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT)"
        )
        # Two cards, four comments each (ids ascending).
        await database.execute("INSERT INTO oc_cards (id, name) VALUES (1, 'A')")
        await database.execute("INSERT INTO oc_cards (id, name) VALUES (2, 'B')")
        cid = 0
        for card in (1, 2):
            for _ in range(4):
                cid += 1
                await database.execute(
                    "INSERT INTO oc_comments (id, card_id, body) VALUES (?, ?, ?)",
                    cid,
                    card,
                    f"c{cid}",
                )
                await database.execute(
                    "INSERT INTO oo_comments (id, card_id, body) VALUES (?, ?, ?)",
                    cid,
                    card,
                    f"c{cid}",
                )
        yield database
        await database.disconnect()

    async def test_per_parent_limit_is_window_top_n(self, ordered_db) -> None:
        """LIMIT 2 ORDER BY id DESC -> each card keeps its OWN top-2, not global 2."""
        cards = await Shape.fetch(OCCard, ordered_db)
        by_id = {c.id: c for c in cards}
        # Card 1's comments are ids 1-4; top-2 by id DESC -> [4, 3].
        assert [cm.id for cm in by_id[1].comments] == [4, 3]
        # Card 2's comments are ids 5-8; top-2 by id DESC -> [8, 7]. Per-parent,
        # NOT a single global LIMIT 2 (which would starve card 2 entirely).
        assert [cm.id for cm in by_id[2].comments] == [8, 7]

    async def test_order_by_preserved_without_limit(self, ordered_db) -> None:
        """ORDER BY (no LIMIT) is re-attached so child order is deterministic."""
        cards = await Shape.fetch(OOCard, ordered_db)
        by_id = {c.id: c for c in cards}
        # All four comments per card, ascending by id (the declared ORDER BY).
        assert [cm.id for cm in by_id[1].comments] == [1, 2, 3, 4]
        assert [cm.id for cm in by_id[2].comments] == [5, 6, 7, 8]

    def test_limit_without_order_by_fails_loud(self) -> None:
        @shape("SELECT id, card_id, body FROM lc WHERE card_id = :card_id LIMIT 3")
        @dataclass(frozen=True, slots=True)
        class LimitNoOrder:
            id: int
            card_id: int
            body: str

        @shape("SELECT id, name FROM lc_cards")
        @dataclass(frozen=True, slots=True)
        class LimitNoOrderParent:
            id: int
            name: str
            kids: tuple[LimitNoOrder, ...] = nested(LimitNoOrder, on="card_id", key="id")

        with pytest.raises(ShapeError, match="ORDER BY"):
            Shape.validate(LimitNoOrderParent)

    def test_offset_fails_loud(self) -> None:
        @shape(
            "SELECT id, card_id, body FROM oc WHERE card_id = :card_id ORDER BY id LIMIT 3 OFFSET 2"
        )
        @dataclass(frozen=True, slots=True)
        class OffsetChild:
            id: int
            card_id: int
            body: str

        @shape("SELECT id, name FROM oc_cards2")
        @dataclass(frozen=True, slots=True)
        class OffsetParent:
            id: int
            name: str
            kids: tuple[OffsetChild, ...] = nested(OffsetChild, on="card_id", key="id")

        with pytest.raises(ShapeError, match="OFFSET"):
            Shape.validate(OffsetParent)

    def test_limit_with_grandchildren_fails_loud(self) -> None:
        @shape("SELECT id, comment_id, txt FROM replies WHERE comment_id = :comment_id")
        @dataclass(frozen=True, slots=True)
        class GCReply:
            id: int
            comment_id: int
            txt: str

        @shape(
            "SELECT id, card_id, body FROM gc_comments WHERE card_id = :card_id ORDER BY id LIMIT 2"
        )
        @dataclass(frozen=True, slots=True)
        class GCComment:
            id: int
            card_id: int
            body: str
            replies: tuple[GCReply, ...] = nested(GCReply, on="comment_id", key="id")

        @shape("SELECT id, name FROM gc_cards")
        @dataclass(frozen=True, slots=True)
        class GCCard:
            id: int
            name: str
            comments: tuple[GCComment, ...] = nested(GCComment, on="card_id", key="id")

        with pytest.raises(ShapeError, match=r"grandchildren|nested"):
            Shape.validate(GCCard)


# -- optional=True nested: skip-None-key branch AND all-None branch ----------


@shape("SELECT id, owner_id, label FROM opt_tags WHERE owner_id = :owner_id")
@dataclass(frozen=True, slots=True)
class OptTag:
    id: int
    owner_id: int
    label: str


@shape("SELECT id, name, group_id FROM opt_items")
@dataclass(frozen=True, slots=True)
class OptItem:
    id: int
    name: str
    group_id: int | None
    tags: tuple[OptTag, ...] = nested(OptTag, on="owner_id", key="group_id", optional=True)


class TestOptionalNested:
    @pytest.fixture
    async def opt_db(self, tmp_path):
        db_path = tmp_path / "opt.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute(
            "CREATE TABLE opt_items (id INTEGER PRIMARY KEY, name TEXT, group_id INTEGER)"
        )
        await database.execute(
            "CREATE TABLE opt_tags (id INTEGER PRIMARY KEY, owner_id INTEGER, label TEXT)"
        )
        yield database
        await database.disconnect()

    async def test_skip_none_key_branch(self, opt_db) -> None:
        """A parent with key=None is skipped; non-None parents still load tags."""
        await opt_db.execute("INSERT INTO opt_items (id, name, group_id) VALUES (1, 'has', 100)")
        await opt_db.execute("INSERT INTO opt_items (id, name, group_id) VALUES (2, 'none', NULL)")
        await opt_db.execute("INSERT INTO opt_tags (id, owner_id, label) VALUES (1, 100, 't1')")
        items = await Shape.fetch(OptItem, opt_db)
        by_id = {i.id: i for i in items}
        assert [t.label for t in by_id[1].tags] == ["t1"]
        # The None-group parent gets an empty tuple (skipped from the IN-list).
        assert by_id[2].tags == ()

    async def test_all_none_key_branch(self, opt_db) -> None:
        """When EVERY parent key is None, no child query runs; all tuples empty."""
        await opt_db.execute("INSERT INTO opt_items (id, name, group_id) VALUES (1, 'a', NULL)")
        await opt_db.execute("INSERT INTO opt_items (id, name, group_id) VALUES (2, 'b', NULL)")
        counting = _CountingDB(opt_db)
        items = await Shape.fetch(OptItem, counting)  # type: ignore[arg-type]
        assert all(i.tags == () for i in items)
        # Only the parent query runs (no key values -> no child IN-list query).
        assert counting.fetch_count == 1


# -- #5: chunking boundary (lowered module constant) -------------------------


class TestChunkingBoundary:
    async def test_keys_exceeding_chunk_size_issue_multiple_batches(
        self, nested_db, monkeypatch
    ) -> None:
        """With _MAX_IN_LIST_KEYS lowered to 2, 3 boards -> the card level chunks."""
        await _seed(nested_db, 3)  # 3 boards, 2 cards each, 2 comments each
        monkeypatch.setattr(_shapes_mod, "_MAX_IN_LIST_KEYS", 2)
        counting = _CountingDB(nested_db)
        boards = await Shape.fetch(NCBoard, counting)  # type: ignore[arg-type]
        assert len(boards) == 3
        # 1 parent query.
        # Card level: 3 distinct board ids / chunk 2 -> 2 batches.
        # Comment level: 6 distinct card ids / chunk 2 -> 3 batches.
        # Total: 1 + 2 + 3 == 6.
        assert counting.fetch_count == 6

    async def test_chunked_merge_is_correct(self, nested_db, monkeypatch) -> None:
        """Chunking merges to the SAME grouped result as a single batch."""
        await _seed(nested_db, 3)
        monkeypatch.setattr(_shapes_mod, "_MAX_IN_LIST_KEYS", 2)
        boards = await Shape.fetch(NCBoard, nested_db)
        by_id = {b.id: b for b in boards}
        for bid, board in by_id.items():
            assert len(board.cards) == 2
            assert all(c.board_id == bid for c in board.cards)
            for card in board.cards:
                assert len(card.comments) == 2
                assert all(cm.card_id == card.id for cm in card.comments)


# -- Postgres ($N) end-to-end through nested compiler + Composite + scope -----


class _FakePGDB:
    """A fake PostgreSQL Database: records bound SQL/params and returns canned rows.

    Reports ``_driver == 'postgresql'`` so _bind_params emits ``$N`` placeholders.
    ``_tables`` maps a (table-name predicate) to canned dict rows; the fake
    filters by the bound params and maps via the real ``map_row`` so the result
    is the same frozen-dataclass shape the production path produces.
    """

    def __init__(self, tables):
        self._tables = tables
        self.statements: list[str] = []

    @property
    def _driver(self) -> str:
        return "postgresql"

    def _rows_for(self, cls, sql):
        from chirp.data._mapping import map_row

        self.statements.append(sql)
        canned = self._tables.get(cls, [])
        return [map_row(cls, row) for row in canned]

    async def fetch(self, cls, sql, /, *params):
        return self._rows_for(cls, sql)

    async def fetch_one(self, cls, sql, /, *params):
        rows = self._rows_for(cls, sql)
        return rows[0] if rows else None


@shape("SELECT id, board_id, title FROM pg_cards WHERE board_id = :board_id", scope="community_id")
@dataclass(frozen=True, slots=True)
class PGCard:
    id: int
    board_id: int
    title: str


@shape("SELECT id, name FROM pg_boards", scope="community_id")
@dataclass(frozen=True, slots=True)
class PGBoard:
    id: int
    name: str
    cards: tuple[PGCard, ...] = nested(PGCard, on="board_id", key="id")


@shape("SELECT id, title FROM pgc_boards WHERE id = :board_id", scope="community_id")
@dataclass(frozen=True, slots=True)
class PGCBoard:
    id: int
    title: str


@composite(scope="community_id")
@dataclass(frozen=True, slots=True)
class PGCPage:
    board: PGCBoard
    cards: tuple[PGCard, ...]


class TestPostgresEndToEnd:
    async def test_nested_compiler_emits_dollar_placeholders(self) -> None:
        fake = _FakePGDB(
            {
                PGBoard: [{"id": 1, "name": "B1"}],
                PGCard: [{"id": 10, "board_id": 1, "title": "C10"}],
            }
        )
        boards = await Shape.fetch(PGBoard, fake, scope=1)  # type: ignore[arg-type]
        assert boards[0].name == "B1"
        assert [c.id for c in boards[0].cards] == [10]
        # Every executed statement uses $N (PG), never a leftover :name token; and
        # the scope predicate ($N) is present in both parent and child queries.
        assert all("$" in s for s in fake.statements)
        assert all(":" not in s for s in fake.statements)
        # Both the parent and the child IN-list query carry the scope predicate.
        assert sum("community_id = $" in s for s in fake.statements) == 2

    async def test_composite_load_pg_threads_scope_dollar(self) -> None:
        fake = _FakePGDB(
            {
                PGCBoard: [{"id": 7, "title": "Owned"}],
                PGCard: [{"id": 10, "board_id": 7, "title": "C10"}],
            }
        )
        page = await Composite.load(PGCPage, fake, board_id=7, scope=1)  # type: ignore[arg-type]
        assert page.board is not None
        assert page.board.title == "Owned"
        assert [c.id for c in page.cards] == [10]
        assert all("$" in s for s in fake.statements)
        assert any("community_id = $" in s for s in fake.statements)


# -- _member_params adversarial (extra ignored, missing fails loud) ----------


class TestMemberParamsAdversarial:
    def test_extra_param_ignored(self) -> None:
        meta = _meta_for(CPMember)
        out = _member_params(meta, None, {"board_id": 7, "irrelevant": "x"})
        # Only :board_id (the placeholder the member SQL references) is kept.
        assert out == {"board_id": 7}

    def test_scope_threaded_when_member_scoped(self) -> None:
        meta = _meta_for(CSCMember)
        out = _member_params(meta, "community_id", {"board_id": 7, "scope": 1})
        assert out == {"board_id": 7, "scope": 1}

    async def test_missing_param_fails_loud_at_fetch(self, composite_db) -> None:
        """A member whose required :name is absent fails loud (not silently)."""
        # CPMember references :board_id; omit it -> _bind_params raises.
        with pytest.raises(ShapeError, match=":board_id"):
            await Shape.fetch(CPMember, composite_db)


def _meta_for(cls):
    """Helper: the frozen _ShapeMeta sidecar for a Shape (test-only accessor)."""
    return cls.__chirp_shape__


# ===========================================================================
# Round-2 adversarial re-audit fixes (A1/A2/A3/A4/A5)
# ===========================================================================


# -- A1: scope-column matcher anchoring (the tenant-isolation BLOCKER) -------


class TestScopeColumnAnchoring:
    def test_suffix_column_is_not_already_scoped(self) -> None:
        """scope='community_id' must NOT substring-match 'actor_community_id'.

        Without a left word boundary, 'WHERE actor_community_id = :scope' was
        judged already-scoped, so the compiler injected NOTHING and shipped an
        UNSCOPED cross-tenant query (and the validate backstop also passed clean).
        """
        sql = "SELECT id FROM t WHERE actor_community_id = :scope"
        # No depth-0 predicate on the *real* scope column is detected.
        assert _depth0_scope_predicate(sql, "community_id") is None
        # The backstop must NOT consider the query already-scoped.
        assert not _has_scope_predicate(sql, "community_id")
        # And injection must add a REAL standalone scope predicate.
        out = _inject_scope(sql, "community_id")
        assert out == (
            "SELECT id FROM t WHERE actor_community_id = :scope AND community_id = :scope"
        )
        # The injected predicate is a standalone scope predicate the backstop sees.
        assert _has_scope_predicate(out, "community_id")

    def test_scope_id_matches_only_bare_id_not_user_id(self) -> None:
        """scope='id' must not match the suffix of '*_id' columns."""
        sql = "SELECT id FROM t WHERE user_id = :uid"
        assert _depth0_scope_predicate(sql, "id") is None
        out = _inject_scope(sql, "id")
        assert out == "SELECT id FROM t WHERE user_id = :uid AND id = :scope"

    def test_org_id_not_false_rejected_by_parent_org_id(self) -> None:
        """scope='org_id' + 'parent_org_id' must inject (no false author-conflict)."""
        sql = "SELECT id FROM t WHERE parent_org_id = :p"
        # parent_org_id is NOT a predicate on the org_id scope column -> inject.
        out = _inject_scope(sql, "org_id")
        assert out == "SELECT id FROM t WHERE parent_org_id = :p AND org_id = :scope"

    def test_real_scope_column_still_idempotent(self) -> None:
        """The genuine scope column (bare or qualified) is still detected."""
        assert _inject_scope("SELECT id FROM t WHERE community_id = :scope", "community_id") == (
            "SELECT id FROM t WHERE community_id = :scope"
        )
        assert _inject_scope("SELECT id FROM t WHERE t.community_id = :scope", "community_id") == (
            "SELECT id FROM t WHERE t.community_id = :scope"
        )

    def test_suffix_column_runtime_leak_excluded(self, tmp_path) -> None:
        """End-to-end: a shape whose WHERE names a *_community_id suffix column
        still gets a REAL tenant predicate injected, so a cross-tenant row is
        excluded at runtime (the leak the suffix bug would have shipped)."""
        import asyncio

        @shape(
            "SELECT id, community_id, actor_community_id, body FROM a1_events "
            "WHERE actor_community_id = :actor",
            scope="community_id",
        )
        @dataclass(frozen=True, slots=True)
        class A1Event:
            id: int
            community_id: int
            actor_community_id: int
            body: str

        async def run() -> list[A1Event]:
            db_path = tmp_path / "a1.db"
            database = Database(f"sqlite:///{db_path}")
            await database.connect()
            await database.execute(
                "CREATE TABLE a1_events (id INTEGER PRIMARY KEY, community_id INTEGER, "
                "actor_community_id INTEGER, body TEXT)"
            )
            # Tenant 1's own row (community_id=1) and a LEAK row owned by tenant 2
            # (community_id=2) but with the SAME actor_community_id=5.
            await database.execute(
                "INSERT INTO a1_events (id, community_id, actor_community_id, body) "
                "VALUES (1, 1, 5, 'mine')"
            )
            await database.execute(
                "INSERT INTO a1_events (id, community_id, actor_community_id, body) "
                "VALUES (2, 2, 5, 'LEAK')"
            )
            try:
                # validate() must pass (compiler output carries the scope predicate).
                Shape.validate(A1Event)
                return await Shape.fetch(A1Event, database, actor=5, scope=1)
            finally:
                await database.disconnect()

        rows = asyncio.run(run())
        # Tenant 1 sees ONLY its own row; the cross-tenant LEAK row is excluded.
        assert [r.id for r in rows] == [1]
        assert all(r.community_id == 1 for r in rows)


# -- A2: comment-aware scanners (no scope into a comment, no phantom binds) ---


class TestCommentAwareScanners:
    def test_placeholder_inside_line_comment_ignored(self) -> None:
        assert _placeholder_names("SELECT id FROM t WHERE a = :a -- :phantom") == {"a"}

    def test_placeholder_inside_block_comment_ignored(self) -> None:
        assert _placeholder_names("SELECT id FROM t /* :phantom */ WHERE a = :a") == {"a"}

    def test_bind_params_ignores_comment_placeholder(self) -> None:
        sql, params = _bind_params("SELECT id FROM t WHERE a = :a -- :phantom", "sqlite", {"a": 7})
        assert sql == "SELECT id FROM t WHERE a = ? -- :phantom"
        assert params == (7,)

    def test_scope_injected_before_trailing_line_comment(self) -> None:
        """The injected predicate must land in EXECUTABLE SQL, not after '--'."""
        out = _inject_scope("SELECT id FROM t WHERE a = :a -- note", "community_id")
        assert out == "SELECT id FROM t WHERE a = :a AND community_id = :scope -- note"
        # The predicate is real SQL (the backstop sees it), not commented out.
        assert _has_scope_predicate(out, "community_id")

    def test_scope_injected_with_inline_block_comment(self) -> None:
        out = _inject_scope("SELECT id FROM t WHERE a = :a /* x */", "community_id")
        assert out == "SELECT id FROM t WHERE a = :a AND community_id = :scope /* x */"
        assert _has_scope_predicate(out, "community_id")

    def test_commented_close_paren_does_not_drive_depth_negative(self) -> None:
        """A commented-out ')' must not make the real WHERE look depth>0."""
        out = _inject_scope("SELECT id FROM t -- )\nWHERE a = :a", "community_id")
        # Exactly one WHERE: the injected predicate joins the real WHERE with AND
        # (no spurious second WHERE from a mis-tracked depth).
        assert out.count("WHERE") == 1
        assert "AND community_id = :scope" in out

    def test_commented_out_where_not_counted_as_second_depth0_where(self) -> None:
        """A commented '/* WHERE x */' is not a second depth-0 WHERE."""
        sql = "SELECT id FROM t /* WHERE x */ WHERE a = :a"
        # Still injectable (only ONE real depth-0 WHERE).
        assert _scope_injectable(sql)
        out = _inject_scope(sql, "community_id")
        assert out == "SELECT id FROM t /* WHERE x */ WHERE a = :a AND community_id = :scope"

    def test_child_order_by_after_comment_with_unbalanced_paren(self) -> None:
        """A child ORDER BY following a comment with a stray ')' is still captured."""
        d = _decompose_child(
            "SELECT id, card_id FROM t /* ) */ WHERE card_id = :card_id ORDER BY id", "card_id"
        )
        assert d.order_by == "id"
        assert d.join_isolated is True

    def test_scope_predicate_inside_line_comment_is_not_already_scoped(self) -> None:
        """A 'community_id = :scope' written inside a '--' comment is NOT real SQL.

        Treating it as an existing predicate would suppress injection and ship an
        UNSCOPED query (the same leak class as A1).
        """
        sql = "SELECT id FROM t WHERE a = :a -- community_id = :scope"
        assert _depth0_scope_predicate(sql, "community_id") is None
        assert not _has_scope_predicate(sql, "community_id")
        out = _inject_scope(sql, "community_id")
        # A REAL predicate is injected before the trailing comment (executable).
        assert "AND community_id = :scope -- community_id = :scope" in out
        assert _has_scope_predicate(out, "community_id")

    def test_scope_predicate_inside_block_comment_is_not_already_scoped(self) -> None:
        sql = "SELECT id FROM t /* community_id = :scope */ WHERE a = :a"
        assert not _has_scope_predicate(sql, "community_id")
        out = _inject_scope(sql, "community_id")
        assert out == (
            "SELECT id FROM t /* community_id = :scope */ WHERE a = :a AND community_id = :scope"
        )

    def test_scope_predicate_inside_string_literal_is_not_already_scoped(self) -> None:
        sql = "SELECT id FROM t WHERE label = 'community_id = :scope' AND a = :a"
        assert not _has_scope_predicate(sql, "community_id")
        out = _inject_scope(sql, "community_id")
        assert "AND community_id = :scope" in out
        assert _has_scope_predicate(out, "community_id")


# -- A3: nested child residual WHERE preserved (runtime row exclusion) --------


@shape(
    "SELECT id, card_id, body, deleted FROM a3_comments WHERE card_id = :card_id AND deleted = 0"
)
@dataclass(frozen=True, slots=True)
class A3Comment:
    id: int
    card_id: int
    body: str
    deleted: int


@shape("SELECT id, name FROM a3_cards")
@dataclass(frozen=True, slots=True)
class A3Card:
    id: int
    name: str
    comments: tuple[A3Comment, ...] = nested(A3Comment, on="card_id", key="id")


@shape(
    "SELECT id, card_id, body, deleted FROM a3_comments "
    "WHERE card_id = :card_id AND deleted = 0 ORDER BY id DESC LIMIT 2"
)
@dataclass(frozen=True, slots=True)
class A3LimitComment:
    id: int
    card_id: int
    body: str
    deleted: int


@shape("SELECT id, name FROM a3_cards")
@dataclass(frozen=True, slots=True)
class A3LimitCard:
    id: int
    name: str
    comments: tuple[A3LimitComment, ...] = nested(A3LimitComment, on="card_id", key="id")


class TestResidualChildWhere:
    @pytest.fixture
    async def a3_db(self, tmp_path):
        db_path = tmp_path / "a3.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE a3_cards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE a3_comments "
            "(id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT, deleted INTEGER)"
        )
        await database.execute("INSERT INTO a3_cards (id, name) VALUES (1, 'A')")
        await database.execute("INSERT INTO a3_cards (id, name) VALUES (2, 'B')")
        # Card 1: 2 live + 1 soft-deleted; card 2: 1 live + 1 soft-deleted.
        rows = [
            (1, 1, "live1", 0),
            (2, 1, "live2", 0),
            (3, 1, "GONE", 1),
            (4, 2, "live3", 0),
            (5, 2, "GONE", 1),
        ]
        for r in rows:
            await database.execute(
                "INSERT INTO a3_comments (id, card_id, body, deleted) VALUES (?, ?, ?, ?)", *r
            )
        yield database
        await database.disconnect()

    def test_batched_sql_preserves_residual_filter(self) -> None:
        sql = _batched_child_sql(A3Comment.__chirp_shape__, "card_id", ("__chirp_k0", "__chirp_k1"))
        assert "card_id IN (:__chirp_k0, :__chirp_k1)" in sql
        # The author's deleted=0 filter survives the IN-list rewrite (finding A3).
        assert "deleted = 0" in sql

    async def test_residual_filter_excludes_rows_at_runtime(self, a3_db) -> None:
        cards = await Shape.fetch(A3Card, a3_db)
        by_id = {c.id: c for c in cards}
        # Soft-deleted comments (ids 3, 5) are excluded by the preserved filter.
        assert sorted(cm.id for cm in by_id[1].comments) == [1, 2]
        assert sorted(cm.id for cm in by_id[2].comments) == [4]
        assert all(cm.deleted == 0 for c in cards for cm in c.comments)

    def test_batched_window_sql_preserves_residual_and_outer_order(self) -> None:
        sql = _batched_child_sql(
            A3LimitComment.__chirp_shape__, "card_id", ("__chirp_k0", "__chirp_k1")
        )
        # Residual filter lives in the inner (pre-ranking) query.
        assert "deleted = 0" in sql
        # The inner derived table ranks by the declared ORDER BY (id DESC).
        assert "ORDER BY id DESC" in sql
        # A4/R3-1: the OUTER select orders on the PROJECTED ``card_id, __chirp_rn``
        # so within-parent order is deterministic without referencing a column the
        # inner derived table might not expose.
        assert sql.rstrip().endswith("ORDER BY card_id, __chirp_rn")
        assert "__chirp_rn <= 2" in sql

    async def test_residual_filter_with_per_parent_limit_window(self, a3_db) -> None:
        """Residual filter + per-parent LIMIT window path excludes soft-deleted."""
        cards = await Shape.fetch(A3LimitCard, a3_db)
        by_id = {c.id: c for c in cards}
        # Card 1 has 2 live comments; top-2 by id DESC -> [2, 1] (GONE id=3 excluded).
        assert [cm.id for cm in by_id[1].comments] == [2, 1]
        # Card 2 has 1 live comment -> [4] (GONE id=5 excluded).
        assert [cm.id for cm in by_id[2].comments] == [4]

    def test_un_isolable_join_predicate_fails_loud(self) -> None:
        @shape("SELECT id, card_id, body FROM uic WHERE card_id = :card_id OR shared = 1")
        @dataclass(frozen=True, slots=True)
        class UnIsolableChild:
            id: int
            card_id: int
            body: str

        @shape("SELECT id, name FROM uic_cards")
        @dataclass(frozen=True, slots=True)
        class UnIsolableParent:
            id: int
            name: str
            kids: tuple[UnIsolableChild, ...] = nested(UnIsolableChild, on="card_id", key="id")

        with pytest.raises(ShapeError, match=r"cannot be cleanly isolated|top-level AND"):
            Shape.validate(UnIsolableParent)


# -- A4: window top-N outer ORDER BY -----------------------------------------


class TestWindowOuterOrderBy:
    def test_window_path_has_outer_order_by(self) -> None:
        meta = _ShapeMeta(
            sql=(
                "SELECT id, card_id, body FROM c WHERE card_id = :card_id "
                "ORDER BY created_at DESC LIMIT 3"
            ),
            columns=("id", "card_id", "body"),
            computed=frozenset(),
            scope=None,
            name="W",
        )
        sql = _batched_child_sql(meta, "card_id", ("__chirp_k0",))
        # The outer SELECT (not just the inner derived table) carries an ORDER BY
        # so within-parent order is not driver-dependent (PostgreSQL warns against
        # relying on inner ORDER BY propagation). But the outer order is on the
        # PROJECTED columns ``{on}, __chirp_rn`` -- NOT the raw ``created_at``,
        # which the inner derived table does not expose (it is ordered/ranked but
        # not SELECTed). Re-emitting ``ORDER BY created_at DESC`` on the outer
        # query would crash with "no such column: created_at" (finding R3-1).
        assert sql.rstrip().endswith("ORDER BY card_id, __chirp_rn")
        # The within-parent order is encoded by __chirp_rn (rank 1 == first by the
        # inner ORDER BY), so the outer query never references the raw sort column.
        assert "ORDER BY created_at" not in sql.rsplit("__chirp_rn <=", 1)[1]
        # The outer ORDER BY sits AFTER the row-number filter.
        assert sql.index("__chirp_rn <=") < sql.rindex("ORDER BY")


# -- A5: chunking x window-top-N interaction ---------------------------------


@shape(
    "SELECT id, card_id, body FROM a5_comments WHERE card_id = :card_id ORDER BY id DESC LIMIT 2"
)
@dataclass(frozen=True, slots=True)
class A5Comment:
    id: int
    card_id: int
    body: str


@shape("SELECT id, name FROM a5_cards")
@dataclass(frozen=True, slots=True)
class A5Card:
    id: int
    name: str
    comments: tuple[A5Comment, ...] = nested(A5Comment, on="card_id", key="id")


class TestChunkingWindowInteraction:
    @pytest.fixture
    async def a5_db(self, tmp_path):
        db_path = tmp_path / "a5.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE a5_cards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE a5_comments (id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT)"
        )
        # 3 cards, 4 comments each (ids ascending, globally unique).
        cid = 0
        for card in (1, 2, 3):
            await database.execute(
                "INSERT INTO a5_cards (id, name) VALUES (?, ?)", card, f"Card {card}"
            )
            for _ in range(4):
                cid += 1
                await database.execute(
                    "INSERT INTO a5_comments (id, card_id, body) VALUES (?, ?, ?)",
                    cid,
                    card,
                    f"c{cid}",
                )
        yield database
        await database.disconnect()

    async def test_per_parent_top_n_correct_across_chunks(self, a5_db, monkeypatch) -> None:
        """Per-parent top-N stays correct when parent keys chunk across batches.

        With _MAX_IN_LIST_KEYS lowered to 2, the 3 card keys span two chunks. Each
        PARTITION BY key lands wholly in ONE chunk (chunking is on the parent
        keys, and a card's comments are all returned by the chunk that includes
        that card's id), so the window top-N is computed correctly per card.
        """
        monkeypatch.setattr(_shapes_mod, "_MAX_IN_LIST_KEYS", 2)
        counting = _CountingDB(a5_db)
        cards = await Shape.fetch(A5Card, counting)  # type: ignore[arg-type]
        by_id = {c.id: c for c in cards}
        # Each card keeps its OWN top-2 by id DESC despite the chunked batches.
        assert [cm.id for cm in by_id[1].comments] == [4, 3]
        assert [cm.id for cm in by_id[2].comments] == [8, 7]
        assert [cm.id for cm in by_id[3].comments] == [12, 11]
        # 1 parent query + ceil(3 / 2) == 2 child window batches.
        assert counting.fetch_count == 3


# -- R3-1: window top-N outer ORDER BY on a NON-projected sort column --------


@shape(
    "SELECT id, card_id, body FROM r31_comments "
    "WHERE card_id = :card_id ORDER BY created_at DESC LIMIT 2"
)
@dataclass(frozen=True, slots=True)
class R31Comment:
    # NOTE: created_at is the ORDER BY column but is deliberately NOT SELECTed /
    # declared -- the canonical "top-N most recent" child. The window rewrite must
    # therefore order the OUTER query on projected columns only (finding R3-1).
    id: int
    card_id: int
    body: str


@shape("SELECT id, name FROM r31_cards")
@dataclass(frozen=True, slots=True)
class R31Card:
    id: int
    name: str
    comments: tuple[R31Comment, ...] = nested(R31Comment, on="card_id", key="id")


class TestWindowOuterOrderByNonProjectedColumn:
    """R3-1: ``ORDER BY <non-projected col> LIMIT N`` must not crash at runtime.

    The inner derived table exposes only the child's declared columns + the
    synthetic ``__chirp_rn``. A top-N child that sorts by a column it does NOT
    SELECT (``ORDER BY created_at DESC`` with no ``created_at`` field) made the
    OLD outer ``ORDER BY created_at`` reference a column the derived table never
    exposes -> "no such column: created_at". The fix orders the outer query on
    ``{on}, __chirp_rn`` (both projected); within-parent order is preserved
    because the inner ROW_NUMBER ranks by the declared ORDER BY.
    """

    @pytest.fixture
    async def r31_db(self, tmp_path):
        db_path = tmp_path / "r31.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE r31_cards (id INTEGER PRIMARY KEY, name TEXT)")
        # created_at exists in the table but is NOT in the child SELECT list.
        await database.execute(
            "CREATE TABLE r31_comments "
            "(id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT, created_at TEXT)"
        )
        await database.execute("INSERT INTO r31_cards (id, name) VALUES (1, 'A')")
        await database.execute("INSERT INTO r31_cards (id, name) VALUES (2, 'B')")
        # Card 1: three comments; created_at ascending with id so id=3 is newest.
        # Card 2: three comments; id=6 is newest. Top-2 by created_at DESC per card.
        rows = [
            (1, 1, "c1", "2024-01-01"),
            (2, 1, "c2", "2024-01-02"),
            (3, 1, "c3", "2024-01-03"),
            (4, 2, "c4", "2024-02-01"),
            (5, 2, "c5", "2024-02-02"),
            (6, 2, "c6", "2024-02-03"),
        ]
        for r in rows:
            await database.execute(
                "INSERT INTO r31_comments (id, card_id, body, created_at) VALUES (?, ?, ?, ?)",
                *r,
            )
        yield database
        await database.disconnect()

    async def test_non_projected_order_column_does_not_crash(self, r31_db) -> None:
        # Before the fix this raised sqlite3.OperationalError: no such column:
        # created_at, surfaced through the Database facade. It must now succeed.
        cards = await Shape.fetch(R31Card, r31_db)
        by_id = {c.id: c for c in cards}
        # Card 1 top-2 most-recent by created_at DESC -> ids [3, 2].
        assert [cm.id for cm in by_id[1].comments] == [3, 2]
        # Card 2 top-2 most-recent -> ids [6, 5]. Per-parent, not a global LIMIT 2.
        assert [cm.id for cm in by_id[2].comments] == [6, 5]


# -- R3-2: author residual placeholder named ``k0`` must not collide ---------


@shape("SELECT id, card_id, body, owner FROM r32_comments WHERE card_id = :card_id AND owner = :k0")
@dataclass(frozen=True, slots=True)
class R32Comment:
    # The residual filter deliberately uses an author placeholder NAMED ``k0`` --
    # the exact name the OLD compiler generated for its first batch key. With the
    # reserved ``__chirp_k0`` prefix it can no longer collide (finding R3-2).
    id: int
    card_id: int
    body: str
    owner: str


@shape("SELECT id, name FROM r32_cards")
@dataclass(frozen=True, slots=True)
class R32Card:
    id: int
    name: str
    comments: tuple[R32Comment, ...] = nested(R32Comment, on="card_id", key="id")


class TestResidualPlaceholderNamedK0:
    """R3-2: an author placeholder named ``k0`` must thread its own value.

    The compiler used to generate batch-key placeholders ``k0, k1, ...`` and seed
    them from the parent keys. An author residual placeholder literally named
    ``:k0`` was NEVER threaded (the loop skipped names already in child_params),
    so it silently bound to a PARENT-KEY value -- ``fetch(id=1, k0='alice')``
    returned ``[]`` because ``:k0`` carried the parent key ``1`` instead of
    ``'alice'``. With the reserved ``__chirp_k0`` prefix the author ``:k0`` is
    threaded from the fetch params and the right rows come back.
    """

    @pytest.fixture
    async def r32_db(self, tmp_path):
        db_path = tmp_path / "r32.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE r32_cards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE r32_comments "
            "(id INTEGER PRIMARY KEY, card_id INTEGER, body TEXT, owner TEXT)"
        )
        await database.execute("INSERT INTO r32_cards (id, name) VALUES (1, 'A')")
        await database.execute("INSERT INTO r32_cards (id, name) VALUES (2, 'B')")
        # Card 1: one alice + one bob; card 2: one alice. The author filter keeps
        # only owner='alice'.
        rows = [
            (1, 1, "by-alice", "alice"),
            (2, 1, "by-bob", "bob"),
            (3, 2, "by-alice-2", "alice"),
        ]
        for r in rows:
            await database.execute(
                "INSERT INTO r32_comments (id, card_id, body, owner) VALUES (?, ?, ?, ?)", *r
            )
        yield database
        await database.disconnect()

    async def test_author_k0_filter_is_applied(self, r32_db) -> None:
        # k0='alice' must filter on owner, NOT collide with the generated batch
        # keys. Before the fix this returned no comments (k0 bound to a card id).
        cards = await Shape.fetch(R32Card, r32_db, k0="alice")
        by_id = {c.id: c for c in cards}
        assert [cm.id for cm in by_id[1].comments] == [1]
        assert all(cm.owner == "alice" for c in cards for cm in c.comments)
        # Card 2's alice comment also comes back -> proves no collision starved it.
        assert [cm.id for cm in by_id[2].comments] == [3]

    async def test_author_k0_filter_excludes_non_matching(self, r32_db) -> None:
        # k0='bob' returns only bob's comment on card 1; card 2 has no bob.
        cards = await Shape.fetch(R32Card, r32_db, k0="bob")
        by_id = {c.id: c for c in cards}
        assert [cm.id for cm in by_id[1].comments] == [2]
        assert by_id[2].comments == ()


# -- R3-3: scoped child author scope-predicate fail-loud parity --------------


@shape(
    "SELECT id, board_id, title FROM r33_cards "
    "WHERE board_id = :board_id AND community_id = :other",
    scope="community_id",
)
@dataclass(frozen=True, slots=True)
class R33ScopedCardAuthorScope:
    # The author wrote their OWN predicate on the scope column (``community_id``)
    # with a non-canonical RHS. On the PARENT path this fails loud; the child path
    # must reach the same fail-loud (finding R3-3) -- the child residual is
    # re-parenthesized at runtime so the depth-0 conflict check would miss it.
    id: int
    board_id: int
    title: str


@shape("SELECT id, name FROM r33_boards", scope="community_id")
@dataclass(frozen=True, slots=True)
class R33Board:
    id: int
    name: str
    cards: tuple[R33ScopedCardAuthorScope, ...] = nested(
        R33ScopedCardAuthorScope, on="board_id", key="id"
    )


class TestScopedChildAuthorPredicateParity:
    """R3-3: a scoped child with an author scope predicate fails loud at validate.

    The parent path already fails loud (``_inject_scope``) when the author wrote
    their own predicate on the scope column. A scoped nested child must reach the
    same fail-loud: at runtime the child's ``community_id = :other`` lands inside
    the IN-list residual parens (depth 1), so the runtime depth-0 conflict check
    misses it and the compiler would silently add ``AND community_id = :scope``
    alongside. ``Shape.validate`` now runs the same injection on the child's
    ORIGINAL SQL so the ambiguity surfaces at startup.
    """

    def test_scoped_child_author_scope_predicate_fails_loud(self) -> None:
        with pytest.raises(ShapeError, match=r"author-written predicate"):
            Shape.validate(R33Board)

    def test_clean_scoped_child_still_validates(self) -> None:
        # Parity check: a scoped child WITHOUT an author scope predicate must
        # still validate cleanly (the new injection is idempotent for it).
        Shape.validate(ScopedBoard)
        Shape.validate(ScopedCard)


# ===========================================================================
# F1 — the reserved ``__chirp_`` placeholder prefix is fail-loud enforced
# ===========================================================================
#
# Round-3 moved generated batch keys to ``__chirp_k0`` / ``__chirp_k1`` ... and
# DOCUMENTED ``__chirp_`` as reserved, but nothing ENFORCED it. An author whose
# DECLARED SQL writes ``:__chirp_k0`` reproduces the exact silent mis-bind the
# prefix was reserved to prevent: ``Shape.validate`` PASSES, but ``Shape.fetch``
# binds ``:__chirp_k0`` to the parent-key value seeded into the batched IN-list,
# returning wrong/empty rows. The author's declared SQL never legitimately
# contains a ``__chirp_`` placeholder, so a fail-loud guard at decoration is safe
# and precise (finding F1).


class TestReservedPlaceholderPrefix:
    def test_reserved_prefix_placeholder_fails_loud_at_decoration(self) -> None:
        # An author residual filter naming a reserved placeholder must fail loud
        # at @shape decoration -- not silently pass validate() then mis-bind at
        # fetch(). Assert the message names the reserved prefix and the offender.
        with pytest.raises(ShapeError) as excinfo:

            @shape(
                "SELECT id, board_id FROM f1_cards "
                "WHERE board_id = :board_id AND owner = :__chirp_k0"
            )
            @dataclass(frozen=True, slots=True)
            class F1ReservedChild:
                id: int
                board_id: int

        msg = str(excinfo.value)
        assert "__chirp_" in msg
        assert "__chirp_k0" in msg
        assert "reserved" in msg.lower()

    def test_reserved_prefix_rejected_on_nested_child_sql(self) -> None:
        # The guard runs at decoration, so it catches a nested CHILD whose SQL
        # uses the reserved prefix even before the parent references it.
        with pytest.raises(ShapeError, match=r"reserved"):

            @shape("SELECT id, card_id FROM f1_kids WHERE card_id = :__chirp_rn")
            @dataclass(frozen=True, slots=True)
            class F1ReservedNestedChild:
                id: int
                card_id: int

    def test_normal_shape_with_ordinary_placeholders_is_unaffected(self) -> None:
        # A normal shape whose placeholders do NOT use the reserved prefix
        # decorates cleanly -- the guard is precise, not blanket.
        @shape("SELECT id, name FROM f1_ok WHERE id = :id AND chirp_owner = :owner")
        @dataclass(frozen=True, slots=True)
        class F1OkShape:
            id: int
            name: str

        # ``chirp_owner`` / ``:owner`` are not under ``__chirp_`` -> fine.
        assert F1OkShape.__chirp_shape__.columns == ("id", "name")

    def test_reserved_prefix_inside_comment_is_not_rejected(self) -> None:
        # The guard scans via the comment-aware shared scanner, so a ``:__chirp_``
        # token inside a comment is NOT a real placeholder and must not fail loud.
        @shape("SELECT id FROM f1_c WHERE id = :id -- not a bind :__chirp_k0")
        @dataclass(frozen=True, slots=True)
        class F1CommentShape:
            id: int

        assert F1CommentShape.__chirp_shape__.columns == ("id",)


# ===========================================================================
# F2 — _scope_injectable keyword gates are comment-aware
# ===========================================================================
#
# R3-5 made _parse_select_columns comment-aware, but the WITH / UNION / INTERSECT
# / EXCEPT / FROM keyword gates in _scope_injectable still ran on RAW SQL, so a
# scoped shape merely MENTIONING one of those keywords inside a comment was
# false-rejected as a compound/opaque query (finding F2).


class TestScopeInjectableCommentAware:
    def test_block_comment_union_is_injectable(self) -> None:
        # ``UNION`` inside a /* ... */ comment is not a compound query.
        sql = "SELECT id, a FROM t /* UNION ALL hack */ WHERE a = :a"
        assert _scope_injectable(sql)

    def test_line_comment_union_is_injectable(self) -> None:
        sql = "SELECT id, a FROM t WHERE a = :a -- UNION SELECT pwd FROM secrets"
        assert _scope_injectable(sql)

    def test_line_comment_with_keyword_scope_injected_correctly(self) -> None:
        # Scope is injected into a query whose comment merely mentions WITH/UNION.
        sql = "SELECT id, a FROM t WHERE a = :a -- WITH cte AS (...) UNION ..."
        out = _inject_scope(sql, "community_id")
        assert "AND community_id = :scope" in out
        assert _has_scope_predicate(out, "community_id")

    def test_block_comment_with_keyword_scope_injected_correctly(self) -> None:
        sql = "SELECT id, a FROM t /* INTERSECT EXCEPT */ WHERE a = :a"
        out = _inject_scope(sql, "community_id")
        assert out == (
            "SELECT id, a FROM t /* INTERSECT EXCEPT */ WHERE a = :a AND community_id = :scope"
        )
        assert _has_scope_predicate(out, "community_id")


# ===========================================================================
# F3 — _inject_scope handles a depth-0 WHERE that begins with a comment
# ===========================================================================
#
# When a scoped WHERE starts with a comment before its first predicate
# (``WHERE -- c\n a = :a`` or ``WHERE /* c */ a = :a``) the old tail-position
# logic treated that leading comment as the WHERE clause's tail boundary and
# produced malformed ``WHERE AND <pred>`` SQL (finding F3).


@shape(
    "SELECT id, community_id, name FROM f3_rows WHERE /* tenant rows only */ name IS NOT NULL",
    scope="community_id",
)
@dataclass(frozen=True, slots=True)
class F3BlockCommentRow:
    id: int
    community_id: int
    name: str


@shape(
    "SELECT id, community_id, name FROM f3_rows\nWHERE -- tenant rows only\n name IS NOT NULL",
    scope="community_id",
)
@dataclass(frozen=True, slots=True)
class F3LineCommentRow:
    id: int
    community_id: int
    name: str


class TestInjectScopeLeadingComment:
    def test_block_comment_after_where_injects_valid_sql(self) -> None:
        out = _inject_scope("SELECT id FROM t WHERE /* c */ a = :a", "community_id")
        # No malformed ``WHERE AND`` -- the predicate lands after ``a = :a``.
        assert "WHERE AND" not in out
        assert "a = :a AND community_id = :scope" in out
        assert _has_scope_predicate(out, "community_id")

    def test_line_comment_after_where_injects_valid_sql(self) -> None:
        out = _inject_scope("SELECT id FROM t WHERE -- c\n a = :a", "community_id")
        assert "WHERE AND" not in out
        assert "a = :a AND community_id = :scope" in out
        assert _has_scope_predicate(out, "community_id")

    async def test_leading_block_comment_scope_executes_and_isolates(self, tmp_path) -> None:
        # DB-EXECUTED: the injected scoped SQL is valid and excludes a cross-tenant
        # row. Proves the leading-comment fix produces EXECUTABLE scoped SQL, not
        # the old malformed ``WHERE AND``.
        db_path = tmp_path / "f3b.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        try:
            await database.execute(
                "CREATE TABLE f3_rows (id INTEGER PRIMARY KEY, community_id INTEGER, name TEXT)"
            )
            await database.execute(
                "INSERT INTO f3_rows (id, community_id, name) VALUES (1, 1, 'mine')"
            )
            await database.execute(
                "INSERT INTO f3_rows (id, community_id, name) VALUES (2, 2, 'theirs')"
            )
            rows = await Shape.fetch(F3BlockCommentRow, database, scope=1)
            assert [r.id for r in rows] == [1]
            assert all(r.community_id == 1 for r in rows)
        finally:
            await database.disconnect()

    async def test_leading_line_comment_scope_executes_and_isolates(self, tmp_path) -> None:
        db_path = tmp_path / "f3l.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        try:
            await database.execute(
                "CREATE TABLE f3_rows (id INTEGER PRIMARY KEY, community_id INTEGER, name TEXT)"
            )
            await database.execute(
                "INSERT INTO f3_rows (id, community_id, name) VALUES (1, 1, 'mine')"
            )
            await database.execute(
                "INSERT INTO f3_rows (id, community_id, name) VALUES (2, 2, 'theirs')"
            )
            rows = await Shape.fetch(F3LineCommentRow, database, scope=1)
            assert [r.id for r in rows] == [1]
            assert all(r.community_id == 1 for r in rows)
        finally:
            await database.disconnect()


# ===========================================================================
# F4 — highest-risk isolation path + window coverage (DB-EXECUTED)
# ===========================================================================
#
# (a) A SCOPED nested child with a per-parent LIMIT window AND a residual filter,
#     all together: a cross-tenant LEAK row that would rank into the top-N if
#     unscoped must NEVER appear (proves scope is injected BEFORE the window
#     ranking). (b) a multi-column window ORDER BY returns the correct per-parent
#     top-N. (c) a parameterized ``LIMIT :n`` window path via Shape.fetch(n=2).


@shape(
    "SELECT id, board_id, community_id, title, archived FROM f4_cards "
    "WHERE board_id = :board_id AND archived = 0 "
    "ORDER BY priority DESC, id DESC LIMIT 2",
    scope="community_id",
)
@dataclass(frozen=True, slots=True)
class F4ScopedWindowChild:
    id: int
    board_id: int
    community_id: int
    title: str
    archived: int


@shape("SELECT id, name FROM f4_boards", scope="community_id")
@dataclass(frozen=True, slots=True)
class F4ScopedWindowBoard:
    id: int
    name: str
    cards: tuple[F4ScopedWindowChild, ...] = nested(F4ScopedWindowChild, on="board_id", key="id")


@shape(
    "SELECT id, board_id, priority, created_at FROM f4_mc "
    "WHERE board_id = :board_id "
    "ORDER BY priority DESC, created_at DESC LIMIT 2"
)
@dataclass(frozen=True, slots=True)
class F4MultiColWindowChild:
    id: int
    board_id: int
    priority: int
    created_at: int


@shape("SELECT id, name FROM f4_mc_boards")
@dataclass(frozen=True, slots=True)
class F4MultiColWindowBoard:
    id: int
    name: str
    items: tuple[F4MultiColWindowChild, ...] = nested(
        F4MultiColWindowChild, on="board_id", key="id"
    )


@shape(
    "SELECT id, board_id, body FROM f4_param WHERE board_id = :board_id ORDER BY id DESC LIMIT :n"
)
@dataclass(frozen=True, slots=True)
class F4ParamLimitChild:
    id: int
    board_id: int
    body: str


@shape("SELECT id, name FROM f4_param_boards")
@dataclass(frozen=True, slots=True)
class F4ParamLimitBoard:
    id: int
    name: str
    items: tuple[F4ParamLimitChild, ...] = nested(F4ParamLimitChild, on="board_id", key="id")


class TestScopedWindowResidualIsolation:
    @pytest.fixture
    async def f4_scoped_db(self, tmp_path):
        db_path = tmp_path / "f4scoped.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        # The board is a SCOPED parent, so the compiler injects community_id into
        # its query too -- the table must carry the scope column.
        await database.execute(
            "CREATE TABLE f4_boards (id INTEGER PRIMARY KEY, community_id INTEGER, name TEXT)"
        )
        await database.execute(
            "CREATE TABLE f4_cards (id INTEGER PRIMARY KEY, board_id INTEGER, "
            "community_id INTEGER, title TEXT, archived INTEGER, priority INTEGER)"
        )
        await database.execute(
            "INSERT INTO f4_boards (id, community_id, name) VALUES (1, 1, 'Board 1')"
        )
        # Tenant 1's own cards on board 1.
        rows = [
            # id, board_id, community_id, title, archived, priority
            (1, 1, 1, "mine-low", 0, 1),
            (2, 1, 1, "mine-high", 0, 5),
            (3, 1, 1, "mine-archived", 1, 9),  # excluded by residual archived=0
            # A cross-tenant LEAK row: HIGHEST priority -> would rank #1 in the
            # per-parent top-2 window if scope were applied AFTER the ranking.
            (99, 1, 2, "LEAK-highest", 0, 99),
        ]
        for r in rows:
            await database.execute(
                "INSERT INTO f4_cards "
                "(id, board_id, community_id, title, archived, priority) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                *r,
            )
        yield database
        await database.disconnect()

    async def test_scope_applied_before_window_excludes_leak(self, f4_scoped_db) -> None:
        # Tenant 1 fetch: the LEAK row (community_id=2, priority=99) would be the
        # window top-1 if scope were applied after ranking. It must NEVER appear,
        # and the archived row (id=3) is excluded by the residual filter. The
        # surviving top-2 by priority DESC, id DESC -> [2 (pri 5), 1 (pri 1)].
        boards = await Shape.fetch(F4ScopedWindowBoard, f4_scoped_db, scope=1)
        assert [b.id for b in boards] == [1]
        card_ids = [c.id for c in boards[0].cards]
        assert 99 not in card_ids
        assert 3 not in card_ids
        assert card_ids == [2, 1]
        assert all(c.community_id == 1 for c in boards[0].cards)


class TestMultiColumnWindowOrder:
    @pytest.fixture
    async def f4_mc_db(self, tmp_path):
        db_path = tmp_path / "f4mc.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE f4_mc_boards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE f4_mc (id INTEGER PRIMARY KEY, board_id INTEGER, "
            "priority INTEGER, created_at INTEGER)"
        )
        for b in (1, 2):
            await database.execute("INSERT INTO f4_mc_boards (id, name) VALUES (?, ?)", b, f"B{b}")
        # Neither priority nor created_at is the projected sort key alone; the
        # window must rank by (priority DESC, created_at DESC).
        rows = [
            # id, board_id, priority, created_at
            (1, 1, 5, 100),
            (2, 1, 5, 200),  # same priority, newer -> ranks above id=1
            (3, 1, 9, 50),  # highest priority -> ranks #1
            (4, 1, 1, 999),
            (5, 2, 2, 10),
            (6, 2, 2, 20),  # newer within same priority -> ranks #1 on board 2
            (7, 2, 1, 30),
        ]
        for r in rows:
            await database.execute(
                "INSERT INTO f4_mc (id, board_id, priority, created_at) VALUES (?, ?, ?, ?)",
                *r,
            )
        yield database
        await database.disconnect()

    async def test_multi_column_window_top_n_per_parent(self, f4_mc_db) -> None:
        boards = await Shape.fetch(F4MultiColWindowBoard, f4_mc_db)
        by_id = {b.id: b for b in boards}
        # Board 1 top-2 by (priority DESC, created_at DESC): id=3 (pri 9), then
        # id=2 (pri 5, created 200 beats id=1's 100).
        assert [it.id for it in by_id[1].items] == [3, 2]
        # Board 2 top-2: id=6 (pri 2, created 20), id=5 (pri 2, created 10).
        assert [it.id for it in by_id[2].items] == [6, 5]


class TestParameterizedLimitWindow:
    @pytest.fixture
    async def f4_param_db(self, tmp_path):
        db_path = tmp_path / "f4param.db"
        database = Database(f"sqlite:///{db_path}")
        await database.connect()
        await database.execute("CREATE TABLE f4_param_boards (id INTEGER PRIMARY KEY, name TEXT)")
        await database.execute(
            "CREATE TABLE f4_param (id INTEGER PRIMARY KEY, board_id INTEGER, body TEXT)"
        )
        for b in (1, 2):
            await database.execute(
                "INSERT INTO f4_param_boards (id, name) VALUES (?, ?)", b, f"B{b}"
            )
        cid = 0
        for board in (1, 2):
            for _ in range(4):
                cid += 1
                await database.execute(
                    "INSERT INTO f4_param (id, board_id, body) VALUES (?, ?, ?)",
                    cid,
                    board,
                    f"c{cid}",
                )
        yield database
        await database.disconnect()

    async def test_parameterized_limit_threaded_through_fetch(self, f4_param_db) -> None:
        # A ``LIMIT :n`` window path: the placeholder is threaded from
        # Shape.fetch(..., n=2) into the per-parent window top-N.
        boards = await Shape.fetch(F4ParamLimitBoard, f4_param_db, n=2)
        by_id = {b.id: b for b in boards}
        # Board 1 ids 1..4 -> top-2 by id DESC == [4, 3]; board 2 ids 5..8 -> [8, 7].
        assert [it.id for it in by_id[1].items] == [4, 3]
        assert [it.id for it in by_id[2].items] == [8, 7]

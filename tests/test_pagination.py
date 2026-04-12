"""Tests for chirp.data.pagination — PageResult + Query.paginate()."""

from dataclasses import dataclass

import pytest

from chirp.data import Database, PageResult, Query

# -- Test model --


@dataclass(frozen=True, slots=True)
class Item:
    id: int
    name: str


# =============================================================================
# PageResult properties (no database needed)
# =============================================================================


class TestPageResult:
    """Test PageResult metadata calculations."""

    def test_total_pages_even_division(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=50)
        assert r.total_pages == 5

    def test_total_pages_with_remainder(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=51)
        assert r.total_pages == 6

    def test_total_pages_zero_total(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=0)
        assert r.total_pages == 1

    def test_total_pages_single_item(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=1)
        assert r.total_pages == 1

    def test_total_pages_per_page_one(self) -> None:
        r = PageResult(items=[], page=1, per_page=1, total=7)
        assert r.total_pages == 7

    def test_has_prev_first_page(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=50)
        assert r.has_prev is False

    def test_has_prev_middle_page(self) -> None:
        r = PageResult(items=[], page=3, per_page=10, total=50)
        assert r.has_prev is True

    def test_has_next_last_page(self) -> None:
        r = PageResult(items=[], page=5, per_page=10, total=50)
        assert r.has_next is False

    def test_has_next_middle_page(self) -> None:
        r = PageResult(items=[], page=3, per_page=10, total=50)
        assert r.has_next is True

    def test_has_next_single_page(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=5)
        assert r.has_next is False

    def test_prev_page_clamped_to_one(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=50)
        assert r.prev_page == 1

    def test_prev_page_normal(self) -> None:
        r = PageResult(items=[], page=3, per_page=10, total=50)
        assert r.prev_page == 2

    def test_next_page_clamped_to_total(self) -> None:
        r = PageResult(items=[], page=5, per_page=10, total=50)
        assert r.next_page == 5

    def test_next_page_normal(self) -> None:
        r = PageResult(items=[], page=3, per_page=10, total=50)
        assert r.next_page == 4

    def test_offset_first_page(self) -> None:
        r = PageResult(items=[], page=1, per_page=20, total=100)
        assert r.offset == 0

    def test_offset_third_page(self) -> None:
        r = PageResult(items=[], page=3, per_page=20, total=100)
        assert r.offset == 40

    def test_page_range_middle(self) -> None:
        r = PageResult(items=[], page=5, per_page=10, total=100)
        assert r.page_range(2) == [3, 4, 5, 6, 7]

    def test_page_range_near_start(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=100)
        assert r.page_range(2) == [1, 2, 3]

    def test_page_range_near_end(self) -> None:
        r = PageResult(items=[], page=10, per_page=10, total=100)
        assert r.page_range(2) == [8, 9, 10]

    def test_page_range_single_page(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=5)
        assert r.page_range(2) == [1]

    def test_page_range_window_zero(self) -> None:
        r = PageResult(items=[], page=5, per_page=10, total=100)
        assert r.page_range(0) == [5]

    def test_page_range_default_window(self) -> None:
        r = PageResult(items=[], page=5, per_page=10, total=100)
        assert r.page_range() == [3, 4, 5, 6, 7]

    def test_frozen(self) -> None:
        r = PageResult(items=[], page=1, per_page=10, total=0)
        with pytest.raises(AttributeError):
            r.page = 2  # type: ignore[misc]


# =============================================================================
# Query.paginate() integration (requires SQLite)
# =============================================================================


@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite database with an items table."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path}")
    await db.connect()
    await db.execute(
        "CREATE TABLE items (  id INTEGER PRIMARY KEY AUTOINCREMENT,  name TEXT NOT NULL)"
    )
    yield db
    await db.disconnect()


@pytest.fixture
async def seeded_db(db):
    """Database with 50 items for pagination testing."""
    for i in range(1, 51):
        await db.execute("INSERT INTO items (name) VALUES (?)", f"Item {i:03d}")
    return db


class TestPaginate:
    """Test Query.paginate() integration."""

    async def test_first_page(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=1, per_page=10)
        assert len(result.items) == 10
        assert result.items[0].name == "Item 001"
        assert result.items[9].name == "Item 010"
        assert result.page == 1
        assert result.per_page == 10
        assert result.total == 50
        assert result.total_pages == 5

    async def test_middle_page(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=3, per_page=10)
        assert len(result.items) == 10
        assert result.items[0].name == "Item 021"
        assert result.items[9].name == "Item 030"
        assert result.has_prev is True
        assert result.has_next is True

    async def test_last_page(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=5, per_page=10)
        assert len(result.items) == 10
        assert result.items[0].name == "Item 041"
        assert result.has_next is False

    async def test_partial_last_page(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=6, per_page=9)
        # 50 items / 9 per page = 6 pages, last page has 5 items
        assert len(result.items) == 5
        assert result.total_pages == 6
        assert result.has_next is False

    async def test_page_beyond_total_returns_empty(self, seeded_db) -> None:
        result = (
            await Query(Item, "items").order_by("id").paginate(seeded_db, page=100, per_page=10)
        )
        assert result.items == []
        assert result.total == 50
        assert result.page == 100

    async def test_page_zero_clamped_to_one(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=0, per_page=10)
        assert result.page == 1
        assert result.items[0].name == "Item 001"

    async def test_negative_page_clamped_to_one(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=-5, per_page=10)
        assert result.page == 1

    async def test_empty_table(self, db) -> None:
        result = await Query(Item, "items").paginate(db, page=1, per_page=10)
        assert result.items == []
        assert result.total == 0
        assert result.total_pages == 1
        assert result.has_prev is False
        assert result.has_next is False

    async def test_with_where_filter(self, seeded_db) -> None:
        # Items named "Item 01X" — there are 10 of them (010-019)
        result = await (
            Query(Item, "items")
            .where("name LIKE ?", "Item 01%")
            .order_by("id")
            .paginate(seeded_db, page=1, per_page=5)
        )
        assert result.total == 10
        assert result.total_pages == 2
        assert len(result.items) == 5
        assert result.items[0].name == "Item 010"

    async def test_with_where_filter_page_two(self, seeded_db) -> None:
        result = await (
            Query(Item, "items")
            .where("name LIKE ?", "Item 01%")
            .order_by("id")
            .paginate(seeded_db, page=2, per_page=5)
        )
        assert len(result.items) == 5
        assert result.items[0].name == "Item 015"
        assert result.has_next is False

    async def test_per_page_one(self, seeded_db) -> None:
        result = await Query(Item, "items").order_by("id").paginate(seeded_db, page=1, per_page=1)
        assert len(result.items) == 1
        assert result.total_pages == 50
        assert result.has_next is True

    async def test_does_not_mutate_original_query(self, seeded_db) -> None:
        """paginate() must not alter the original Query's limit/offset."""
        q = Query(Item, "items").order_by("id")
        await q.paginate(seeded_db, page=3, per_page=10)
        assert q._limit is None
        assert q._offset is None

    async def test_default_per_page(self, seeded_db) -> None:
        result = await Query(Item, "items").paginate(seeded_db)
        assert result.per_page == 20
        assert len(result.items) == 20

    async def test_where_if_and_paginate(self, seeded_db) -> None:
        """Dynamic filters compose cleanly with paginate — no duplicate queries."""
        search = "Item 00"
        result = await (
            Query(Item, "items")
            .where_if(search, "name LIKE ?", f"%{search}%")
            .order_by("id")
            .paginate(seeded_db, page=1, per_page=5)
        )
        # "Item 00X" matches Items 001-009 = 9 items
        assert result.total == 9
        assert result.total_pages == 2

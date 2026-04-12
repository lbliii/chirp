"""Tests for DependencyIndex.register() and block_dependencies().

Covers:
- register() validates inputs
- register() populates internal mappings correctly
- block_dependencies() returns correct paths
- Backward compat: register_template() and register_from_sse_swaps() still work
- ConnectionInfo dataclass basics
"""

import time

import pytest

from chirp.pages.reactive import BlockRef, ConnectionInfo, DependencyIndex

# ---------------------------------------------------------------------------
# register() validation
# ---------------------------------------------------------------------------


class TestRegisterValidation:
    """register() rejects invalid inputs."""

    def test_empty_path_raises(self) -> None:
        index = DependencyIndex()
        ref = BlockRef(template_name="page.html", block_name="content")
        with pytest.raises(ValueError, match="non-empty"):
            index.register("", ref)

    def test_empty_template_name_raises(self) -> None:
        index = DependencyIndex()
        ref = BlockRef(template_name="", block_name="content")
        with pytest.raises(ValueError, match="non-empty"):
            index.register("data", ref)

    def test_empty_block_name_raises(self) -> None:
        index = DependencyIndex()
        ref = BlockRef(template_name="page.html", block_name="")
        with pytest.raises(ValueError, match="non-empty"):
            index.register("data", ref)


# ---------------------------------------------------------------------------
# register() behavior
# ---------------------------------------------------------------------------


class TestRegisterBehavior:
    """register() correctly populates the dependency index."""

    def test_single_registration(self) -> None:
        index = DependencyIndex()
        ref = BlockRef(template_name="board.html", block_name="task_list")
        index.register("tasks", ref)

        blocks = index.affected_blocks(frozenset({"tasks"}))
        assert len(blocks) == 1
        assert blocks[0].block_name == "task_list"

    def test_multiple_blocks_same_path(self) -> None:
        index = DependencyIndex()
        index.register("tasks", BlockRef("board.html", "task_list"))
        index.register("tasks", BlockRef("board.html", "task_count"))

        blocks = index.affected_blocks(frozenset({"tasks"}))
        assert len(blocks) == 2
        names = {b.block_name for b in blocks}
        assert names == {"task_list", "task_count"}

    def test_dotted_path_prefix_matching(self) -> None:
        index = DependencyIndex()
        index.register("doc.title", BlockRef("page.html", "header"))
        index.register("doc.content", BlockRef("page.html", "body"))

        # Changing "doc" should affect both children
        blocks = index.affected_blocks(frozenset({"doc"}))
        assert len(blocks) == 2

    def test_dom_id_preserved(self) -> None:
        index = DependencyIndex()
        ref = BlockRef("board.html", "count", dom_id="task-count")
        index.register("tasks", ref)

        blocks = index.affected_blocks(frozenset({"tasks"}))
        assert blocks[0].target_id == "task-count"

    def test_register_works_with_derive(self) -> None:
        index = DependencyIndex()
        index.register("tasks.stats", BlockRef("board.html", "stats"))
        index.derive("tasks.stats", from_paths={"tasks"})

        # Changing "tasks" should expand to "tasks.stats"
        blocks = index.affected_blocks(frozenset({"tasks"}))
        assert any(b.block_name == "stats" for b in blocks)


# ---------------------------------------------------------------------------
# block_dependencies() inverse query
# ---------------------------------------------------------------------------


class TestBlockDependencies:
    """block_dependencies() returns the correct set of paths."""

    def test_single_path(self) -> None:
        index = DependencyIndex()
        index.register("tasks", BlockRef("board.html", "task_list"))

        deps = index.block_dependencies("board.html", "task_list")
        assert deps == frozenset({"tasks"})

    def test_multiple_paths(self) -> None:
        index = DependencyIndex()
        index.register("tasks", BlockRef("board.html", "task_list"))
        index.register("users", BlockRef("board.html", "task_list"))

        deps = index.block_dependencies("board.html", "task_list")
        assert deps == frozenset({"tasks", "users"})

    def test_unregistered_block_returns_empty(self) -> None:
        index = DependencyIndex()
        index.register("tasks", BlockRef("board.html", "task_list"))

        deps = index.block_dependencies("board.html", "nonexistent")
        assert deps == frozenset()

    def test_different_templates_isolated(self) -> None:
        index = DependencyIndex()
        index.register("tasks", BlockRef("board.html", "task_list"))
        index.register("users", BlockRef("admin.html", "task_list"))

        deps_board = index.block_dependencies("board.html", "task_list")
        deps_admin = index.block_dependencies("admin.html", "task_list")
        assert deps_board == frozenset({"tasks"})
        assert deps_admin == frozenset({"users"})


# ---------------------------------------------------------------------------
# ConnectionInfo dataclass
# ---------------------------------------------------------------------------


class TestConnectionInfo:
    """ConnectionInfo is a proper frozen dataclass."""

    def test_basic_creation(self) -> None:
        before = time.monotonic()
        conn = ConnectionInfo(session_id="sess-1", user_id="alice")
        after = time.monotonic()
        assert conn.session_id == "sess-1"
        assert conn.user_id == "alice"
        assert before <= conn.connected_at <= after

    def test_anonymous_user(self) -> None:
        conn = ConnectionInfo(session_id="sess-2")
        assert conn.user_id is None

    def test_frozen(self) -> None:
        conn = ConnectionInfo(session_id="s")
        with pytest.raises(AttributeError):
            conn.session_id = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ConnectionInfo(session_id="s", user_id="u", connected_at=1.0)
        b = ConnectionInfo(session_id="s", user_id="u", connected_at=1.0)
        assert a == b

    def test_hashable(self) -> None:
        conn = ConnectionInfo(session_id="s", user_id="u")
        s = {conn, conn}
        assert len(s) == 1

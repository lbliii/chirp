"""Tests for reactive bus contract rules.

Covers:
- check_reactive_block_existence: block refs vs real template blocks
- check_reactive_derivation_dag: cycle detection in derivation graph
"""

from kida import Environment, FileSystemLoader

from chirp.contracts.rules_reactive import (
    check_reactive_block_existence,
    check_reactive_derivation_dag,
)
from chirp.pages.reactive.events import BlockRef
from chirp.pages.reactive.index import DependencyIndex

# ---------------------------------------------------------------------------
# Block existence
# ---------------------------------------------------------------------------


class TestReactiveBlockExistence:
    """BlockRef references must point to real template blocks."""

    def test_valid_block_passes(self, tmp_path):
        (tmp_path / "board.html").write_text(
            "{% block task_list %}<ul></ul>{% endblock %}"
            "{% block task_count %}<span>0</span>{% endblock %}"
        )
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()
        index._path_to_blocks.setdefault("tasks", []).append(
            BlockRef(template_name="board.html", block_name="task_list")
        )
        index._path_to_blocks["tasks"].append(
            BlockRef(template_name="board.html", block_name="task_count")
        )

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 0

    def test_missing_block_reports_error(self, tmp_path):
        (tmp_path / "board.html").write_text(
            "{% block task_list %}<ul></ul>{% endblock %}"
        )
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()
        index._path_to_blocks.setdefault("tasks", []).append(
            BlockRef(template_name="board.html", block_name="taks_list")  # typo
        )

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 1
        assert issues[0].severity.value == "error"
        assert issues[0].category == "reactive_block"
        assert "taks_list" in issues[0].message
        assert "task_list" in issues[0].message  # suggests available blocks

    def test_missing_template_reports_error(self, tmp_path):
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()
        index._path_to_blocks.setdefault("tasks", []).append(
            BlockRef(template_name="nonexistent.html", block_name="body")
        )

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 1
        assert "could not be loaded" in issues[0].message

    def test_empty_index_no_issues(self, tmp_path):
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 0

    def test_duplicate_refs_checked_once(self, tmp_path):
        """Same (template, block) registered under multiple paths is checked once."""
        (tmp_path / "page.html").write_text(
            "{% block status %}<span>ok</span>{% endblock %}"
        )
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()
        ref = BlockRef(template_name="page.html", block_name="status")
        index._path_to_blocks.setdefault("a", []).append(ref)
        index._path_to_blocks.setdefault("b", []).append(ref)

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 0

    def test_multiple_templates_mixed_valid_invalid(self, tmp_path):
        (tmp_path / "a.html").write_text("{% block good %}<p>ok</p>{% endblock %}")
        (tmp_path / "b.html").write_text("{% block other %}<p>x</p>{% endblock %}")
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        index = DependencyIndex()
        index._path_to_blocks.setdefault("x", []).append(
            BlockRef(template_name="a.html", block_name="good")
        )
        index._path_to_blocks["x"].append(
            BlockRef(template_name="b.html", block_name="missing")
        )

        issues = check_reactive_block_existence(index, env)
        assert len(issues) == 1
        assert "b.html" in issues[0].template


# ---------------------------------------------------------------------------
# Derivation DAG
# ---------------------------------------------------------------------------


class TestReactiveDerivationDag:
    """Derivation graph must be acyclic."""

    def test_no_derivations_passes(self):
        index = DependencyIndex()
        issues = check_reactive_derivation_dag(index)
        assert len(issues) == 0

    def test_linear_chain_passes(self):
        index = DependencyIndex()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"b"})
        issues = check_reactive_derivation_dag(index)
        assert len(issues) == 0

    def test_diamond_passes(self):
        index = DependencyIndex()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"a"})
        index.derive("d", from_paths={"b", "c"})
        issues = check_reactive_derivation_dag(index)
        assert len(issues) == 0

    def test_simple_cycle_detected(self):
        index = DependencyIndex()
        index.derive("a", from_paths={"b"})
        index.derive("b", from_paths={"a"})
        issues = check_reactive_derivation_dag(index)
        assert len(issues) == 1
        assert issues[0].category == "reactive_cycle"
        assert "a" in issues[0].message
        assert "b" in issues[0].message

    def test_self_cycle_detected(self):
        index = DependencyIndex()
        index.derive("x", from_paths={"x"})
        issues = check_reactive_derivation_dag(index)
        assert len(issues) == 1
        assert "x" in issues[0].message

    def test_three_node_cycle_detected(self):
        index = DependencyIndex()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"b"})
        index.derive("a", from_paths={"c"})
        issues = check_reactive_derivation_dag(index)
        assert len(issues) >= 1
        assert all(i.category == "reactive_cycle" for i in issues)

    def test_cycle_is_warning_not_error(self):
        index = DependencyIndex()
        index.derive("a", from_paths={"b"})
        index.derive("b", from_paths={"a"})
        issues = check_reactive_derivation_dag(index)
        assert issues[0].severity.value == "warning"

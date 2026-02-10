"""Tests for DependencyIndex derived path propagation.

Covers the full test matrix:

- Direct derivation
- Transitive chains
- Multi-source derivation
- Cycle safety
- Prefix interaction
- No derivations (zero overhead)
- No matching blocks (graceful empty)
- Additive merging of derive() calls
"""

from chirp.pages.reactive import BlockRef, DependencyIndex


def _make_index(*blocks: tuple[str, str, list[str]]) -> DependencyIndex:
    """Build a DependencyIndex from (template, block, [dep_paths]) tuples.

    Bypasses kida entirely — registers blocks directly into the
    internal ``_path_to_blocks`` mapping for fast, isolated tests.
    """
    index = DependencyIndex()
    for template, block, dep_paths in blocks:
        ref = BlockRef(template_name=template, block_name=block)
        for path in dep_paths:
            index._path_to_blocks.setdefault(path, []).append(ref)
    return index


def _block_names(refs: list[BlockRef]) -> set[str]:
    """Extract block names from a list of BlockRef for easy assertion."""
    return {ref.block_name for ref in refs}


# ---------------------------------------------------------------------------
# Direct derivation
# ---------------------------------------------------------------------------


class TestDirectDerivation:
    """Changing a source path invalidates blocks on the derived path."""

    def test_derived_block_included(self):
        index = _make_index(
            ("t.html", "word_count_display", ["doc.word_count"]),
        )
        index.derive("doc.word_count", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"word_count_display"}

    def test_source_still_matches_its_own_blocks(self):
        index = _make_index(
            ("t.html", "editor", ["doc.content"]),
            ("t.html", "word_count_display", ["doc.word_count"]),
        )
        index.derive("doc.word_count", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"editor", "word_count_display"}

    def test_unrelated_path_not_affected(self):
        index = _make_index(
            ("t.html", "word_count_display", ["doc.word_count"]),
        )
        index.derive("doc.word_count", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.title"}))
        assert result == []


# ---------------------------------------------------------------------------
# Transitive chains
# ---------------------------------------------------------------------------


class TestTransitiveChains:
    """A -> B -> C: changing C invalidates blocks on A."""

    def test_two_level_chain(self):
        index = _make_index(
            ("t.html", "summary_display", ["doc.summary"]),
        )
        # doc.summary derives from doc.word_count
        # doc.word_count derives from doc.content
        index.derive("doc.word_count", from_paths={"doc.content"})
        index.derive("doc.summary", from_paths={"doc.word_count"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"summary_display"}

    def test_three_level_chain(self):
        index = _make_index(
            ("t.html", "final", ["d"]),
        )
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"b"})
        index.derive("d", from_paths={"c"})

        result = index.affected_blocks(frozenset({"a"}))
        assert _block_names(result) == {"final"}

    def test_intermediate_blocks_also_included(self):
        index = _make_index(
            ("t.html", "count_block", ["doc.word_count"]),
            ("t.html", "summary_block", ["doc.summary"]),
        )
        index.derive("doc.word_count", from_paths={"doc.content"})
        index.derive("doc.summary", from_paths={"doc.word_count"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"count_block", "summary_block"}


# ---------------------------------------------------------------------------
# Multi-source derivation
# ---------------------------------------------------------------------------


class TestMultiSource:
    """D derives from {A, B} — changing either invalidates D's blocks."""

    def test_first_source(self):
        index = _make_index(
            ("t.html", "summary", ["doc.summary"]),
        )
        index.derive("doc.summary", from_paths={"doc.content", "doc.title"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"summary"}

    def test_second_source(self):
        index = _make_index(
            ("t.html", "summary", ["doc.summary"]),
        )
        index.derive("doc.summary", from_paths={"doc.content", "doc.title"})

        result = index.affected_blocks(frozenset({"doc.title"}))
        assert _block_names(result) == {"summary"}

    def test_both_sources_no_duplicates(self):
        index = _make_index(
            ("t.html", "summary", ["doc.summary"]),
        )
        index.derive("doc.summary", from_paths={"doc.content", "doc.title"})

        result = index.affected_blocks(frozenset({"doc.content", "doc.title"}))
        assert _block_names(result) == {"summary"}
        assert len(result) == 1  # no duplicates


# ---------------------------------------------------------------------------
# Cycle safety
# ---------------------------------------------------------------------------


class TestCycleSafety:
    """Cycles in the derivation graph terminate without infinite loops."""

    def test_simple_cycle(self):
        index = _make_index(
            ("t.html", "block_a", ["a"]),
            ("t.html", "block_b", ["b"]),
        )
        index.derive("b", from_paths={"a"})
        index.derive("a", from_paths={"b"})

        result = index.affected_blocks(frozenset({"a"}))
        assert _block_names(result) == {"block_a", "block_b"}

    def test_self_cycle(self):
        index = _make_index(
            ("t.html", "block_a", ["a"]),
        )
        index.derive("a", from_paths={"a"})

        result = index.affected_blocks(frozenset({"a"}))
        assert _block_names(result) == {"block_a"}

    def test_three_node_cycle(self):
        index = _make_index(
            ("t.html", "block_a", ["a"]),
            ("t.html", "block_b", ["b"]),
            ("t.html", "block_c", ["c"]),
        )
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"b"})
        index.derive("a", from_paths={"c"})

        result = index.affected_blocks(frozenset({"a"}))
        assert _block_names(result) == {"block_a", "block_b", "block_c"}


# ---------------------------------------------------------------------------
# Prefix interaction
# ---------------------------------------------------------------------------


class TestPrefixInteraction:
    """Derived paths interact correctly with prefix matching."""

    def test_derived_child_matches_parent_block(self):
        """Block depends on 'stats', derive 'stats.word_count' from 'doc.content'.

        Changing 'doc.content' expands to include 'stats.word_count'.
        Prefix matching then sees that 'stats.word_count' starts with 'stats.'
        and invalidates blocks depending on 'stats'.
        """
        index = _make_index(
            ("t.html", "stats_panel", ["stats"]),
        )
        index.derive("stats.word_count", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"stats_panel"}

    def test_derived_parent_matches_child_block(self):
        """Block depends on 'stats.word_count', derive 'stats' from 'doc.content'.

        Changing 'doc.content' expands to include 'stats'.
        Prefix matching then sees that 'stats.word_count' starts with 'stats.'
        """
        index = _make_index(
            ("t.html", "wc_display", ["stats.word_count"]),
        )
        index.derive("stats", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"wc_display"}


# ---------------------------------------------------------------------------
# No derivations (zero overhead)
# ---------------------------------------------------------------------------


class TestNoDerivations:
    """When no derivations are registered, behavior is unchanged."""

    def test_direct_match_still_works(self):
        index = _make_index(
            ("t.html", "toolbar", ["doc.version"]),
        )
        result = index.affected_blocks(frozenset({"doc.version"}))
        assert _block_names(result) == {"toolbar"}

    def test_prefix_match_still_works(self):
        index = _make_index(
            ("t.html", "doc_block", ["doc"]),
        )
        result = index.affected_blocks(frozenset({"doc.version"}))
        assert _block_names(result) == {"doc_block"}

    def test_no_match_returns_empty(self):
        index = _make_index(
            ("t.html", "toolbar", ["doc.version"]),
        )
        result = index.affected_blocks(frozenset({"user.name"}))
        assert result == []

    def test_source_to_derived_empty(self):
        index = _make_index()
        assert index._source_to_derived == {}


# ---------------------------------------------------------------------------
# No matching blocks
# ---------------------------------------------------------------------------


class TestNoMatchingBlocks:
    """Derived path expands but no blocks depend on it — empty, no error."""

    def test_expansion_with_no_dependent_blocks(self):
        index = _make_index(
            ("t.html", "editor", ["doc.content"]),
        )
        # Derive word_count from content, but no blocks depend on word_count
        index.derive("doc.word_count", from_paths={"doc.content"})

        # Only the editor block (which depends on doc.content) is returned
        result = index.affected_blocks(frozenset({"doc.content"}))
        assert _block_names(result) == {"editor"}

    def test_only_derived_path_changed_no_blocks(self):
        index = _make_index()
        # No blocks registered at all
        index.derive("doc.word_count", from_paths={"doc.content"})

        result = index.affected_blocks(frozenset({"doc.content"}))
        assert result == []


# ---------------------------------------------------------------------------
# Additive merging
# ---------------------------------------------------------------------------


class TestAdditiveMerging:
    """Multiple derive() calls for the same path merge source sets."""

    def test_two_calls_merge(self):
        index = _make_index(
            ("t.html", "summary", ["doc.summary"]),
        )
        index.derive("doc.summary", from_paths={"doc.content"})
        index.derive("doc.summary", from_paths={"doc.title"})

        # Both sources should trigger the derived path
        result_content = index.affected_blocks(frozenset({"doc.content"}))
        result_title = index.affected_blocks(frozenset({"doc.title"}))
        assert _block_names(result_content) == {"summary"}
        assert _block_names(result_title) == {"summary"}

    def test_derivations_property_shows_merged(self):
        index = _make_index()
        index.derive("doc.summary", from_paths={"doc.content"})
        index.derive("doc.summary", from_paths={"doc.title"})

        derivations = index.derivations
        assert derivations == {
            "doc.summary": frozenset({"doc.content", "doc.title"}),
        }


# ---------------------------------------------------------------------------
# _expand_paths unit tests
# ---------------------------------------------------------------------------


class TestExpandPaths:
    """Direct tests of the BFS expansion."""

    def test_no_derivations_returns_input(self):
        index = _make_index()
        paths = frozenset({"a", "b"})
        assert index._expand_paths(paths) == paths

    def test_single_expansion(self):
        index = _make_index()
        index.derive("b", from_paths={"a"})
        assert index._expand_paths(frozenset({"a"})) == frozenset({"a", "b"})

    def test_transitive_expansion(self):
        index = _make_index()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"b"})
        assert index._expand_paths(frozenset({"a"})) == frozenset({"a", "b", "c"})

    def test_diamond_expansion(self):
        """A -> B, A -> C, B -> D, C -> D: D appears once."""
        index = _make_index()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"a"})
        index.derive("d", from_paths={"b", "c"})
        assert index._expand_paths(frozenset({"a"})) == frozenset({"a", "b", "c", "d"})

    def test_cycle_terminates(self):
        index = _make_index()
        index.derive("b", from_paths={"a"})
        index.derive("a", from_paths={"b"})
        assert index._expand_paths(frozenset({"a"})) == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# derivations property
# ---------------------------------------------------------------------------


class TestDerivationsProperty:
    """The derivations property returns {derived: frozenset(sources)}."""

    def test_empty(self):
        index = _make_index()
        assert index.derivations == {}

    def test_single(self):
        index = _make_index()
        index.derive("b", from_paths={"a"})
        assert index.derivations == {"b": frozenset({"a"})}

    def test_multiple_sources(self):
        index = _make_index()
        index.derive("c", from_paths={"a", "b"})
        assert index.derivations == {"c": frozenset({"a", "b"})}

    def test_multiple_derived(self):
        index = _make_index()
        index.derive("b", from_paths={"a"})
        index.derive("c", from_paths={"a"})
        assert index.derivations == {
            "b": frozenset({"a"}),
            "c": frozenset({"a"}),
        }


# ---------------------------------------------------------------------------
# explain_affected
# ---------------------------------------------------------------------------


class TestExplainAffected:
    """The explain_affected() debug helper returns a complete breakdown."""

    def test_with_derivation(self):
        index = _make_index(
            ("t.html", "wc", ["doc.word_count"]),
        )
        index.derive("doc.word_count", from_paths={"doc.content"})

        info = index.explain_affected(frozenset({"doc.content"}))
        assert info["original_paths"] == frozenset({"doc.content"})
        assert info["expanded_paths"] == frozenset({"doc.content", "doc.word_count"})
        assert info["derived_paths"] == frozenset({"doc.word_count"})
        assert len(info["affected_blocks"]) == 1
        assert info["affected_blocks"][0]["block"] == "wc"

    def test_without_derivation(self):
        index = _make_index(
            ("t.html", "toolbar", ["doc.version"]),
        )

        info = index.explain_affected(frozenset({"doc.version"}))
        assert info["original_paths"] == frozenset({"doc.version"})
        assert info["expanded_paths"] == frozenset({"doc.version"})
        assert info["derived_paths"] == frozenset()
        assert len(info["affected_blocks"]) == 1

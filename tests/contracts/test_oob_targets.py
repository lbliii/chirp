"""Tests for OOB swap target validation.

Covers check_oob_targets: cross-references hx-swap-oob IDs against
the set of all static element IDs found in templates.
"""

from chirp.contracts.rules_oob_targets import check_oob_targets


class TestOOBTargets:
    """hx-swap-oob target IDs must exist in some template."""

    def test_valid_oob_target_passes(self):
        sources = {
            "page.html": '<div id="status">ok</div>',
            "fragment.html": '<div hx-swap-oob="true" id="status"><span>updated</span></div>',
        }
        all_ids = {"status"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 0

    def test_missing_oob_target_warns(self):
        sources = {
            "fragment.html": '<div hx-swap-oob="true" id="stauts"><span>updated</span></div>',
        }
        all_ids = {"status"}  # note: "stauts" not in set
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 1
        assert issues[0].severity.value == "warning"
        assert issues[0].category == "oob_target"
        assert "stauts" in issues[0].message

    def test_id_before_oob_attribute(self):
        """id= can appear before hx-swap-oob= in the tag."""
        sources = {
            "f.html": '<span id="count" hx-swap-oob="innerHTML">42</span>',
        }
        all_ids = {"count"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 0

    def test_id_before_oob_missing_warns(self):
        sources = {
            "f.html": '<span id="cunt" hx-swap-oob="innerHTML">42</span>',
        }
        all_ids = {"count"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 1
        assert "cunt" in issues[0].message

    def test_dynamic_id_skipped(self):
        """IDs containing Kida expressions are not checked."""
        sources = {
            "f.html": '<div hx-swap-oob="true" id="{{ item.id }}">x</div>',
        }
        all_ids: set[str] = set()
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 0

    def test_no_oob_elements_no_issues(self):
        sources = {
            "page.html": '<div id="content"><p>Hello</p></div>',
        }
        all_ids = {"content"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 0

    def test_multiple_oob_targets_mixed(self):
        sources = {
            "f.html": (
                '<div hx-swap-oob="true" id="good">ok</div>'
                '<div hx-swap-oob="true" id="bad">fail</div>'
            ),
        }
        all_ids = {"good"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 1
        assert "bad" in issues[0].message

    def test_oob_with_swap_strategy(self):
        """hx-swap-oob can have values like 'innerHTML', 'outerHTML', etc."""
        sources = {
            "f.html": '<div hx-swap-oob="innerHTML" id="nav">links</div>',
        }
        all_ids = {"nav"}
        issues = check_oob_targets(sources, all_ids)
        assert len(issues) == 0

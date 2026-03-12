"""Tests for HTMX selector syntax validation."""

from chirp.contracts import Severity
from chirp.contracts.rules_htmx import check_selector_syntax


class TestSelectorSyntaxValidation:
    """Validate malformed selector syntax for HTMX selector attributes."""

    def test_errors_for_quoted_selector_literal(self):
        issues = check_selector_syntax(
            {"page.html": '<button hx-post="/x" hx-target="\'#result\'">Run</button>'}
        )
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "selector_syntax"
        assert "wrapped in quotes" in issues[0].message

    def test_errors_for_unbalanced_selector(self):
        issues = check_selector_syntax({"page.html": '<div hx-select="#panel["></div>'})
        assert len(issues) == 1
        assert "unbalanced" in issues[0].message

    def test_errors_for_empty_selector_list_entry(self):
        issues = check_selector_syntax({"page.html": '<div hx-include="#a,,#b"></div>'})
        assert len(issues) == 1
        assert "empty entry" in issues[0].message

    def test_skips_dynamic_selector_values(self):
        issues = check_selector_syntax(
            {"page.html": '<div hx-target="{{ target_selector }}"></div>'}
        )
        assert issues == []

    def test_allows_selector_command_prefixes(self):
        issues = check_selector_syntax(
            {"page.html": '<button hx-target="closest .card"></button>'}
        )
        assert issues == []

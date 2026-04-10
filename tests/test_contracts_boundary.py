"""Tests for the error boundary coverage contract check."""

from chirp.contracts.rules_boundary import check_boundary_coverage
from chirp.contracts.types import Severity


class TestBoundaryCoverage:
    def test_warns_oob_block_without_try(self) -> None:
        source = (
            '<div hx-swap-oob="true" id="stats">'
            "{% block stats %}<p>{{ count }}</p>{% endblock %}"
            "</div>"
        )
        issues = check_boundary_coverage({"page.html": source})
        assert len(issues) == 1
        assert issues[0].severity == Severity.INFO
        assert issues[0].category == "boundary"
        assert "stats" in issues[0].message
        assert issues[0].template == "page.html"

    def test_no_issue_when_try_present(self) -> None:
        source = (
            '<div hx-swap-oob="true" id="stats">'
            "{% block stats %}{% try %}<p>{{ count }}</p>"
            "{% fallback %}<p>--</p>{% end %}{% endblock %}"
            "</div>"
        )
        issues = check_boundary_coverage({"page.html": source})
        assert len(issues) == 0

    def test_ignores_templates_without_oob(self) -> None:
        source = "{% block content %}<p>Hello</p>{% endblock %}"
        issues = check_boundary_coverage({"page.html": source})
        assert len(issues) == 0

    def test_ignores_chirp_internal_templates(self) -> None:
        source = '<div hx-swap-oob="true">{% block x %}hi{% endblock %}</div>'
        issues = check_boundary_coverage({"chirp/base.html": source})
        assert len(issues) == 0
        issues = check_boundary_coverage({"chirpui/shell.html": source})
        assert len(issues) == 0

    def test_multiple_blocks_mixed_coverage(self) -> None:
        source = (
            '<div hx-swap-oob="innerHTML">'
            "{% block covered %}{% try %}ok{% fallback %}err{% end %}{% endblock %}"
            "{% block uncovered %}<p>data</p>{% endblock %}"
            "</div>"
        )
        issues = check_boundary_coverage({"page.html": source})
        assert len(issues) == 1
        assert "uncovered" in issues[0].message

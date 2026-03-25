"""Tests for the Vary header contract rule."""

from chirp.contracts.rules_vary import check_vary_coverage
from chirp.contracts.types import Severity


class TestVaryCoverage:
    def test_detects_is_fragment_branch(self) -> None:
        source = "{% if is_fragment %}<div>fragment</div>{% else %}<html>full</html>{% endif %}"
        issues = check_vary_coverage({"app/page.html": source})
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "vary"
        assert "is_fragment" in issues[0].message

    def test_detects_request_htmx_branch(self) -> None:
        source = "{% if request.htmx %}<div>htmx</div>{% endif %}"
        issues = check_vary_coverage({"app/page.html": source})
        assert len(issues) == 1

    def test_detects_request_is_fragment_branch(self) -> None:
        source = "{% if request.is_fragment %}<div>frag</div>{% endif %}"
        issues = check_vary_coverage({"app/page.html": source})
        assert len(issues) == 1

    def test_ignores_chirp_internal_templates(self) -> None:
        source = "{% if is_fragment %}internal{% endif %}"
        issues = check_vary_coverage({"chirp/base.html": source})
        assert len(issues) == 0

    def test_ignores_chirpui_templates(self) -> None:
        source = "{% if is_fragment %}internal{% endif %}"
        issues = check_vary_coverage({"chirpui/shell.html": source})
        assert len(issues) == 0

    def test_no_issue_for_normal_templates(self) -> None:
        source = "<div>{{ title }}</div>"
        issues = check_vary_coverage({"app/page.html": source})
        assert len(issues) == 0

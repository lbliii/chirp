"""Tests for accessibility rule — hx-* on non-interactive elements."""

from chirp.contracts import Severity
from chirp.contracts.rules_accessibility import check_accessibility


class TestCheckAccessibility:
    """_check_accessibility warns on hx-* attrs on non-interactive elements."""

    def test_div_with_hx_get_warns(self):
        html = '<div hx-get="/items">load</div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "accessibility"
        assert "<div>" in issues[0].message
        assert issues[0].template == "test.html"

    def test_span_with_hx_post_warns(self):
        html = '<span class="btn" hx-post="/submit">go</span>'
        issues = check_accessibility(html, "form.html")
        assert len(issues) == 1
        assert "<span>" in issues[0].message

    def test_button_is_interactive_no_warning(self):
        html = '<button hx-post="/submit">go</button>'
        issues = check_accessibility(html, "form.html")
        assert len(issues) == 0

    def test_a_tag_is_interactive_no_warning(self):
        html = '<a hx-get="/page" hx-push-url="true">link</a>'
        issues = check_accessibility(html, "nav.html")
        assert len(issues) == 0

    def test_input_is_interactive_no_warning(self):
        html = '<input hx-get="/search" hx-trigger="keyup">'
        issues = check_accessibility(html, "search.html")
        assert len(issues) == 0

    def test_form_is_interactive_no_warning(self):
        html = '<form hx-post="/submit">...</form>'
        issues = check_accessibility(html, "form.html")
        assert len(issues) == 0

    def test_div_with_role_no_warning(self):
        html = '<div role="button" hx-get="/items">load</div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_div_with_tabindex_no_warning(self):
        html = '<div tabindex="0" hx-get="/items">load</div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_div_with_role_and_tabindex_no_warning(self):
        html = '<div role="button" tabindex="0" hx-post="/action">do</div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_multiple_elements_mixed(self):
        html = """
        <button hx-post="/ok">good</button>
        <div hx-get="/bad">bad</div>
        <a hx-get="/fine">fine</a>
        <span hx-delete="/also-bad">bad</span>
        <li role="button" hx-get="/ok-with-role">ok</li>
        """
        issues = check_accessibility(html, "mixed.html")
        # Only <div> and <span> should warn (li has role)
        assert len(issues) == 2
        messages = [i.message for i in issues]
        assert any("<div>" in m for m in messages)
        assert any("<span>" in m for m in messages)

    def test_no_hx_url_attrs_no_warnings(self):
        html = '<div class="container"><span>text</span></div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_section_with_hx_get_warns(self):
        html = '<section hx-get="/content">loading...</section>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 1
        assert "<section>" in issues[0].message

    def test_tr_with_hx_get_warns(self):
        html = '<tr hx-get="/row/1">...</tr>'
        issues = check_accessibility(html, "table.html")
        assert len(issues) == 1
        assert "<tr>" in issues[0].message

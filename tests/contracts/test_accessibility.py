"""Tests for accessibility contract checks.

- ``a11y_interactive``: hx-* on non-interactive elements
- ``a11y_label``: form fields without associated labels
"""

from chirp.contracts import Severity
from chirp.contracts.rules_accessibility import (
    check_accessibility,
    check_label_association,
)

# ---------------------------------------------------------------------------
# a11y_interactive
# ---------------------------------------------------------------------------


class TestCheckAccessibility:
    """check_accessibility warns on hx-* attrs on non-interactive elements."""

    def test_div_with_hx_get_warns(self):
        html = '<div hx-get="/items">load</div>'
        issues = check_accessibility(html, "test.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "a11y_interactive"
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


# ---------------------------------------------------------------------------
# a11y_label — form fields without associated labels
# ---------------------------------------------------------------------------


class TestCheckLabelAssociation:
    """check_label_association warns on form fields without labels."""

    # -- Label-for association --

    def test_input_with_label_for_no_warning(self):
        html = '<label for="name">Name</label><input id="name" name="name">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_input_without_label_warns(self):
        html = '<input type="text" id="email" name="email">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "a11y_label"
        assert "email" in issues[0].message
        assert issues[0].template == "form.html"

    def test_select_without_label_warns(self):
        html = '<select id="role" name="role"><option>Admin</option></select>'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 1
        assert "<select>" in issues[0].message

    def test_textarea_without_label_warns(self):
        html = '<textarea id="bio" name="bio"></textarea>'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 1
        assert "<textarea>" in issues[0].message

    def test_select_with_label_for_no_warning(self):
        html = '<label for="role">Role</label><select id="role" name="role"></select>'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_textarea_with_label_for_no_warning(self):
        html = '<label for="bio">Bio</label><textarea id="bio" name="bio"></textarea>'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    # -- Wrapping label --

    def test_input_inside_label_no_warning(self):
        html = "<label>Name <input type='text' name='name'></label>"
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_checkbox_inside_label_no_warning(self):
        html = '<label><input type="checkbox" name="agree"> I agree</label>'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_select_inside_label_no_warning(self):
        html = "<label>Color <select name='color'><option>Red</option></select></label>"
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    # -- aria-label / aria-labelledby --

    def test_input_with_aria_label_no_warning(self):
        html = '<input type="text" name="q" aria-label="Search">'
        issues = check_label_association(html, "search.html")
        assert len(issues) == 0

    def test_input_with_aria_labelledby_no_warning(self):
        html = '<input type="text" name="q" aria-labelledby="search-heading">'
        issues = check_label_association(html, "search.html")
        assert len(issues) == 0

    # -- Exempt types --

    def test_hidden_input_exempt(self):
        html = '<input type="hidden" name="csrf" value="abc">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_submit_input_exempt(self):
        html = '<input type="submit" value="Save">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_button_input_exempt(self):
        html = '<input type="button" value="Cancel">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_image_input_exempt(self):
        html = '<input type="image" src="go.png" alt="Go">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    def test_reset_input_exempt(self):
        html = '<input type="reset" value="Reset">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 0

    # -- Kida template expressions --

    def test_kida_expression_in_for_and_id_matches(self):
        """{{ name }} in both for and id should be treated as matching."""
        html = '<label for="{{ name }}">Label</label><input id="{{ name }}" name="{{ name }}">'
        issues = check_label_association(html, "macro.html")
        assert len(issues) == 0

    def test_kida_expression_only_in_id_no_match(self):
        """{{ name }} in id but literal in for — still matches via wildcard."""
        html = '<label for="{{ name }}">Label</label><input id="{{ field_name }}" name="x">'
        issues = check_label_association(html, "macro.html")
        # Both normalize to __KIDA__, so they match
        assert len(issues) == 0

    def test_kida_expression_no_label_at_all_warns(self):
        html = '<input id="{{ name }}" name="{{ name }}">'
        issues = check_label_association(html, "macro.html")
        assert len(issues) == 1

    # -- Multiple fields --

    def test_multiple_fields_mixed(self):
        html = """
        <label for="name">Name</label>
        <input id="name" name="name">
        <input type="text" name="email">
        <input type="hidden" name="csrf">
        <label><input type="checkbox" name="agree"> Agree</label>
        <select name="role"><option>Admin</option></select>
        """
        issues = check_label_association(html, "form.html")
        # email (no label) and select role (no label) should warn
        assert len(issues) == 2
        messages = [i.message for i in issues]
        assert any("email" in m for m in messages)
        assert any("role" in m for m in messages)

    # -- No inputs at all --

    def test_no_form_elements_no_warnings(self):
        html = "<div><p>Hello world</p></div>"
        issues = check_label_association(html, "page.html")
        assert len(issues) == 0

    # -- Input with no name or id still warns --

    def test_input_with_no_name_or_id_warns(self):
        html = '<input type="text">'
        issues = check_label_association(html, "form.html")
        assert len(issues) == 1
        assert "<input>" in issues[0].message

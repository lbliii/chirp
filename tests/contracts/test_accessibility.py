"""Tests for accessibility contract checks.

- ``a11y_interactive``: hx-* on non-interactive elements
- ``a11y_label``: form fields without associated labels
- ``a11y_alt``: images without alt attribute
- ``a11y_heading``: heading levels that skip
- ``a11y_landmark``: layout templates missing <main>
"""

from chirp.contracts import Severity
from chirp.contracts.rules_accessibility import (
    check_accessibility,
    check_heading_order,
    check_image_alt,
    check_label_association,
    check_landmarks,
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


# ---------------------------------------------------------------------------
# a11y_alt — images without alt attribute
# ---------------------------------------------------------------------------


class TestCheckImageAlt:
    """check_image_alt warns on <img> tags missing alt."""

    def test_img_without_alt_warns(self):
        html = '<img src="photo.jpg">'
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "a11y_alt"
        assert "photo.jpg" in issues[0].message
        assert issues[0].template == "page.html"

    def test_img_with_alt_no_warning(self):
        html = '<img src="photo.jpg" alt="A photo">'
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 0

    def test_img_with_empty_alt_no_warning(self):
        """Empty alt="" is valid for decorative images."""
        html = '<img src="decorative.png" alt="">'
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 0

    def test_self_closing_img_without_alt_warns(self):
        html = '<img src="icon.svg" />'
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 1

    def test_multiple_images_mixed(self):
        html = """
        <img src="good.jpg" alt="Good">
        <img src="bad.jpg">
        <img src="also-bad.png">
        <img src="ok.gif" alt="">
        """
        issues = check_image_alt(html, "gallery.html")
        assert len(issues) == 2
        messages = [i.message for i in issues]
        assert any("bad.jpg" in m for m in messages)
        assert any("also-bad.png" in m for m in messages)

    def test_no_images_no_warnings(self):
        html = "<div><p>No images here</p></div>"
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 0

    def test_img_no_src_warns_with_generic_desc(self):
        html = "<img>"
        issues = check_image_alt(html, "page.html")
        assert len(issues) == 1
        assert "<img>" in issues[0].message


# ---------------------------------------------------------------------------
# a11y_heading — heading levels that skip
# ---------------------------------------------------------------------------


class TestCheckHeadingOrder:
    """check_heading_order warns when heading levels skip."""

    def test_h1_to_h3_warns(self):
        html = "<h1>Title</h1><h3>Subsection</h3>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "a11y_heading"
        assert "<h1>" in issues[0].message
        assert "<h3>" in issues[0].message
        assert issues[0].template == "page.html"

    def test_h1_h2_h3_no_warning(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 0

    def test_descending_levels_no_warning(self):
        """Going from h3 back to h1 is fine (new section)."""
        html = "<h1>A</h1><h2>B</h2><h3>C</h3><h1>D</h1>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 0

    def test_h2_to_h4_warns(self):
        html = "<h2>Section</h2><h4>Deep</h4>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 1
        assert "<h2>" in issues[0].message
        assert "<h4>" in issues[0].message

    def test_multiple_skips(self):
        html = "<h1>A</h1><h3>B</h3><h6>C</h6>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 2

    def test_no_headings_no_warnings(self):
        html = "<p>Just a paragraph</p>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 0

    def test_single_heading_no_warning(self):
        html = "<h2>Only heading</h2>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 0

    def test_same_level_repeated_no_warning(self):
        html = "<h2>A</h2><h2>B</h2><h2>C</h2>"
        issues = check_heading_order(html, "page.html")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# a11y_landmark — layout templates missing <main>
# ---------------------------------------------------------------------------


class TestCheckLandmarks:
    """check_landmarks warns when layout templates lack <main>."""

    def test_layout_without_main_warns(self):
        sources = {"_layout.html": "<html><body>{% block content %}{% endblock %}</body></html>"}
        issues = check_landmarks(sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "a11y_landmark"
        assert issues[0].template == "_layout.html"

    def test_layout_with_main_no_warning(self):
        sources = {
            "_layout.html": "<html><body><main>{% block content %}{% endblock %}</main></body></html>"
        }
        issues = check_landmarks(sources)
        assert len(issues) == 0

    def test_layout_with_role_main_no_warning(self):
        sources = {
            "_layout.html": '<html><body><div role="main">{% block content %}{% endblock %}</div></body></html>'
        }
        issues = check_landmarks(sources)
        assert len(issues) == 0

    def test_multiple_layouts_mixed(self):
        sources = {
            "_layout.html": "<html><body><main>{% block content %}{% endblock %}</main></body></html>",
            "admin/_layout.html": "<html><body>{% block content %}{% endblock %}</body></html>",
        }
        issues = check_landmarks(sources)
        assert len(issues) == 1
        assert issues[0].template == "admin/_layout.html"

    def test_empty_sources_no_warnings(self):
        issues = check_landmarks({})
        assert len(issues) == 0

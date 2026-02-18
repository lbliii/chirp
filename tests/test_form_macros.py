"""Tests for chirp form field template macros.

Renders each macro with a kida Environment backed by PackageLoader
and verifies the HTML output, error display, and CSS classes.
"""

from dataclasses import dataclass

from kida import Environment, PackageLoader

from chirp.templating.filters import BUILTIN_FILTERS


def _make_env() -> Environment:
    """Create a kida env that can load chirp form macros."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    return env


def _render(env: Environment, source: str, **ctx: object) -> str:
    """Render a template string that imports chirp form macros."""
    tpl = env.from_string(source)
    return tpl.render(ctx).strip()


# ---------------------------------------------------------------------------
# text_field
# ---------------------------------------------------------------------------


class TestTextField:
    def test_basic_render(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("title", "Hello", label="Title") }}',
        )
        assert '<input type="text"' in html
        assert 'name="title"' in html
        assert 'id="title"' in html
        assert 'value="Hello"' in html
        assert "<label" in html
        assert "Title</label>" in html

    def test_no_label(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}{{ text_field("email") }}',
        )
        assert "<label" not in html

    def test_required_attribute(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("name", required=true) }}',
        )
        assert "required" in html

    def test_placeholder(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("name", placeholder="Enter name") }}',
        )
        assert 'placeholder="Enter name"' in html

    def test_error_display(self) -> None:
        env = _make_env()
        errors = {"title": ["Title is required."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("title", errors=errors) }}',
            errors=errors,
        )
        assert "field--error" in html
        assert "field-error" in html
        assert "Title is required." in html

    def test_no_errors_no_error_class(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}{{ text_field("title") }}',
        )
        assert "field--error" not in html
        assert "field-error" not in html

    def test_custom_type(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("password", type="password") }}',
        )
        assert 'type="password"' in html

    def test_multiple_errors(self) -> None:
        env = _make_env()
        errors = {"name": ["Too short.", "No spaces allowed."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("name", errors=errors) }}',
            errors=errors,
        )
        assert "Too short." in html
        assert "No spaces allowed." in html

    def test_errors_for_different_field_no_error_class(self) -> None:
        """Errors dict present but no errors for *this* field — no error styling."""
        env = _make_env()
        errors = {"email": ["Invalid email."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import text_field %}'
            '{{ text_field("name", errors=errors) }}',
            errors=errors,
        )
        assert "field--error" not in html
        assert "field-error" not in html
        assert "Invalid email." not in html


# ---------------------------------------------------------------------------
# textarea_field
# ---------------------------------------------------------------------------


class TestTextareaField:
    def test_basic_render(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import textarea_field %}'
            '{{ textarea_field("desc", "Some text", label="Description") }}',
        )
        assert "<textarea" in html
        assert 'name="desc"' in html
        assert 'id="desc"' in html
        assert "Some text</textarea>" in html
        assert "Description</label>" in html

    def test_rows_attribute(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import textarea_field %}'
            '{{ textarea_field("desc", rows=8) }}',
        )
        assert 'rows="8"' in html

    def test_error_display(self) -> None:
        env = _make_env()
        errors = {"desc": ["Too long."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import textarea_field %}'
            '{{ textarea_field("desc", errors=errors) }}',
            errors=errors,
        )
        assert "field--error" in html
        assert "Too long." in html


# ---------------------------------------------------------------------------
# select_field
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelectOption:
    value: str
    label: str


class TestSelectField:
    def test_basic_render(self) -> None:
        env = _make_env()
        options = [SelectOption("a", "Alpha"), SelectOption("b", "Beta")]
        html = _render(
            env,
            '{% from "chirp/forms.html" import select_field %}'
            '{{ select_field("priority", options, label="Priority") }}',
            options=options,
        )
        assert "<select" in html
        assert 'name="priority"' in html
        assert 'value="a"' in html
        assert "Alpha" in html
        assert "Beta" in html
        assert "Priority</label>" in html

    def test_selected_option(self) -> None:
        env = _make_env()
        options = [SelectOption("low", "Low"), SelectOption("high", "High")]
        html = _render(
            env,
            '{% from "chirp/forms.html" import select_field %}'
            '{{ select_field("prio", options, selected="high") }}',
            options=options,
        )
        # The "high" option should have "selected"
        assert "selected" in html

    def test_error_display(self) -> None:
        env = _make_env()
        options = [SelectOption("a", "A")]
        errors = {"status": ["Invalid status."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import select_field %}'
            '{{ select_field("status", options, errors=errors) }}',
            options=options,
            errors=errors,
        )
        assert "field--error" in html
        assert "Invalid status." in html


# ---------------------------------------------------------------------------
# checkbox_field
# ---------------------------------------------------------------------------


class TestCheckboxField:
    def test_unchecked(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import checkbox_field %}'
            '{{ checkbox_field("agree", label="I agree") }}',
        )
        assert 'type="checkbox"' in html
        assert 'name="agree"' in html
        assert "I agree" in html
        assert "checked" not in html

    def test_checked(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import checkbox_field %}'
            '{{ checkbox_field("agree", checked=true, label="I agree") }}',
        )
        assert "checked" in html

    def test_error_display(self) -> None:
        env = _make_env()
        errors = {"agree": ["Must agree."]}
        html = _render(
            env,
            '{% from "chirp/forms.html" import checkbox_field %}'
            '{{ checkbox_field("agree", errors=errors) }}',
            errors=errors,
        )
        assert "field--error" in html
        assert "Must agree." in html

    def test_fallback_label_to_name(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import checkbox_field %}{{ checkbox_field("newsletter") }}',
        )
        assert "newsletter" in html


# ---------------------------------------------------------------------------
# hidden_field
# ---------------------------------------------------------------------------


class TestHiddenField:
    def test_basic_render(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import hidden_field %}'
            '{{ hidden_field("csrf_token", "abc123") }}',
        )
        assert 'type="hidden"' in html
        assert 'name="csrf_token"' in html
        assert 'value="abc123"' in html

    def test_empty_value(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/forms.html" import hidden_field %}{{ hidden_field("id") }}',
        )
        assert 'name="id"' in html
        assert 'value=""' in html

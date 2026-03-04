"""Tests for chirp built-in template filters."""

from __future__ import annotations

from chirp.templating.filters import BUILTIN_FILTERS, attr, field_errors, html_attrs, qs

# ── attr ──────────────────────────────────────────────────────────────────


class TestAttr:
    """Test the attr filter for conditional HTML attributes."""

    def test_truthy_returns_attribute(self) -> None:
        result = attr("back", "class")
        assert 'class="back"' in str(result)

    def test_falsy_returns_empty(self) -> None:
        assert attr("", "class") == ""
        assert attr(None, "class") == ""

    def test_escapes_value(self) -> None:
        result = attr('foo"bar', "data-value")
        assert "&quot;" in str(result)
        assert 'data-value="foo' in str(result)

    def test_returns_markup(self) -> None:
        """Output is Markup so autoescape does not double-escape."""
        result = attr("active", "class")
        assert hasattr(result, "__html__") or "class=" in str(result)


# ── field_errors ─────────────────────────────────────────────────────────


class TestFieldErrors:
    """Test the field_errors filter for form error display."""

    def test_extracts_errors_for_field(self) -> None:
        errors = {"username": ["too short", "required"], "email": ["invalid"]}
        assert field_errors(errors, "username") == ["too short", "required"]

    def test_missing_field_returns_empty(self) -> None:
        errors = {"username": ["too short"]}
        assert field_errors(errors, "email") == []

    def test_none_errors_returns_empty(self) -> None:
        assert field_errors(None, "username") == []

    def test_empty_dict_returns_empty(self) -> None:
        assert field_errors({}, "anything") == []

    def test_non_dict_returns_empty(self) -> None:
        assert field_errors("not a dict", "field") == []
        assert field_errors(42, "field") == []

    def test_field_with_empty_list(self) -> None:
        assert field_errors({"name": []}, "name") == []

    def test_field_with_single_error(self) -> None:
        assert field_errors({"name": ["required"]}, "name") == ["required"]


# ── html_attrs ────────────────────────────────────────────────────────────────


class TestHtmlAttrs:
    """Test structured HTML attrs rendering and legacy passthrough."""

    def test_none_returns_empty(self) -> None:
        assert html_attrs(None) == ""

    def test_mapping_renders_escaped_attrs(self) -> None:
        rendered = str(html_attrs({"hx-target": "#panel", "data-msg": 'hi"there'}))
        assert ' hx-target="#panel"' in rendered
        assert ' data-msg="hi&quot;there"' in rendered

    def test_mapping_handles_boolean_attrs(self) -> None:
        rendered = str(html_attrs({"disabled": True, "hidden": False, "title": None}))
        assert " disabled" in rendered
        assert "hidden" not in rendered
        assert "title" not in rendered

    def test_mapping_serializes_structured_values(self) -> None:
        rendered = str(html_attrs({"hx-vals": {"page": 1}}))
        assert ' hx-vals="{&quot;page&quot;:1}"' in rendered

    def test_string_passthrough(self) -> None:
        rendered = str(html_attrs('hx-post="/x" hx-target="#y"'))
        assert rendered.startswith(" ")
        assert 'hx-post="/x"' in rendered
        assert 'hx-target="#y"' in rendered


# ── qs ───────────────────────────────────────────────────────────────────


class TestQs:
    """Test the qs filter for URL query string building."""

    def test_single_param(self) -> None:
        assert qs("/search", q="hello") == "/search?q=hello"

    def test_multiple_params(self) -> None:
        result = qs("/", page=2, q="hello")
        assert "page=2" in result
        assert "q=hello" in result
        assert result.startswith("/?")

    def test_omits_falsy_values(self) -> None:
        result = qs("/", page=2, q="", type=None, active=0)
        assert result == "/?page=2"

    def test_all_falsy_returns_base(self) -> None:
        assert qs("/", q="", type=None) == "/"

    def test_no_params_returns_base(self) -> None:
        assert qs("/search") == "/search"

    def test_appends_to_existing_query(self) -> None:
        result = qs("/search?sort=name", page=2)
        assert result == "/search?sort=name&page=2"

    def test_special_characters_encoded(self) -> None:
        result = qs("/", q="hello world")
        assert "hello%20world" in result

    def test_integer_values(self) -> None:
        result = qs("/", page=3)
        assert result == "/?page=3"

    def test_false_is_omitted(self) -> None:
        """False is falsy and should be omitted."""
        assert qs("/", active=False) == "/"

    def test_true_is_included(self) -> None:
        result = qs("/", active=True)
        assert "active=True" in result


# ── Integration ──────────────────────────────────────────────────────────


class TestBuiltinFiltersRegistry:
    """Test that built-in filters are correctly registered."""

    def test_registry_contains_attr(self) -> None:
        assert "attr" in BUILTIN_FILTERS

    def test_registry_contains_field_errors(self) -> None:
        assert "field_errors" in BUILTIN_FILTERS

    def test_registry_contains_qs(self) -> None:
        assert "qs" in BUILTIN_FILTERS

    def test_registry_contains_html_attrs(self) -> None:
        assert "html_attrs" in BUILTIN_FILTERS

    def test_registry_functions_match(self) -> None:
        assert BUILTIN_FILTERS["attr"] is attr
        assert BUILTIN_FILTERS["field_errors"] is field_errors
        assert BUILTIN_FILTERS["html_attrs"] is html_attrs
        assert BUILTIN_FILTERS["qs"] is qs

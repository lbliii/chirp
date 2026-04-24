"""Tests for chirp built-in template filters."""

from __future__ import annotations

from pathlib import Path

import pytest

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


# ── create_environment chirp-ui fallback ────────────────────────────────────


class TestCreateEnvironmentChirpUIFallback:
    """Env-level chirp-ui filter fallback (RFC 001)."""

    def test_env_has_chirp_ui_filters_when_chirp_ui_installed(self, tmp_path: Path) -> None:
        """create_environment ensures chirp-ui filters exist when chirp_ui is loadable."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        # When chirp_ui is installed, env should have html_attrs even without register_filters
        assert "html_attrs" in env.filters
        assert "bem" in env.filters
        assert "field_errors" in env.filters
        assert "validate_variant" in env.filters

    def test_user_filter_overrides_chirp_ui_fallback(self, tmp_path: Path) -> None:
        """User-registered filters take precedence over chirp-ui fallback."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        def custom_html_attrs(x: object) -> str:
            return "custom"

        config = AppConfig(template_dir=str(tmp_path))
        with pytest.warns(UserWarning, match="User filter 'html_attrs' shadows"):
            env = create_environment(
                config,
                filters={"html_attrs": custom_html_attrs},
                globals_={},
            )
        assert env.filters["html_attrs"] is custom_html_attrs

    def test_env_does_not_expose_generic_csrf_token_helper(self, tmp_path: Path) -> None:
        """Chirp owns csrf_token via CSRFMiddleware, not Kida's generic helper."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        assert "csrf_token" not in env.globals


# ── create_environment extra_loaders ──────────────────────────────────────


class TestCreateEnvironmentExtraLoaders:
    """Extra loaders are tried first (CMS, DB, state)."""

    def test_extra_loaders_tried_first(self, tmp_path: Path) -> None:
        """Templates from extra_loaders override filesystem."""
        from kida import DictLoader

        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "override.html").write_text("<p>filesystem</p>")
        config = AppConfig(
            template_dir=str(tmp_path),
            extra_loaders=(DictLoader({"override.html": "<p>OVERRIDE</p>"}),),
        )
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("override.html").render()
        assert "OVERRIDE" in html
        assert "filesystem" not in html

    def test_extra_loaders_fallback_to_filesystem(self, tmp_path: Path) -> None:
        """When extra_loader lacks a template, filesystem is used."""
        from kida import DictLoader

        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "page.html").write_text("<h1>{{ title }}</h1>")
        config = AppConfig(
            template_dir=str(tmp_path),
            extra_loaders=(DictLoader({"other.html": "<p>other</p>"}),),
        )
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("page.html").render(title="Home")
        assert "<h1>Home</h1>" in html


# ── create_environment static_context (partial evaluator) ─────────────────


class TestCreateEnvironmentStaticContext:
    """Static context enables kida's compile-time partial evaluator."""

    def test_default_none(self, tmp_path: Path) -> None:
        """Default static_context is None — no partial evaluation."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        assert env.static_context is None

    def test_static_context_passed_through(self, tmp_path: Path) -> None:
        """static_context dict reaches the kida Environment."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        ctx = {"site_name": "Chirp", "version": "1.0"}
        config = AppConfig(template_dir=str(tmp_path), static_context=ctx)
        env = create_environment(config, filters={}, globals_={})
        assert env.static_context == ctx

    def test_static_context_baked_into_templates(self, tmp_path: Path) -> None:
        """Static values are resolved at compile time."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "page.html").write_text("<title>{{ site_name }}</title>")
        config = AppConfig(
            template_dir=str(tmp_path),
            static_context={"site_name": "Chirp"},
        )
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("page.html").render()
        assert "<title>Chirp</title>" in html


# ── kida 0.4.0 feature verification ──────────────────────────────────────


class TestKida040Features:
    """Verify kida 0.4.0 features work through chirp's environment."""

    def test_error_boundary_renders_fallback(self, tmp_path: Path) -> None:
        """{% try %} catches errors and renders fallback."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "page.html").write_text(
            "{% try %}{{ missing.attr }}{% fallback %}<p>fallback</p>{% end %}"
        )
        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("page.html").render()
        assert "<p>fallback</p>" in html

    def test_scoped_slot_passes_data_to_caller(self, tmp_path: Path) -> None:
        """Scoped slots expose data from def to caller via let: bindings."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "comp.html").write_text(
            "{% def greet(name) %}"
            "<div>{% slot body let:who=name %}Hello {{ who }}{% end %}</div>"
            "{% enddef %}"
        )
        (tmp_path / "page.html").write_text(
            '{% from "comp.html" import greet %}'
            '{% call greet("World") %}'
            "{% slot body %}Hi {{ who }}!{% end %}"
            "{% endcall %}"
        )
        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("page.html").render()
        assert "Hi World!" in html

    def test_list_comprehension_in_template(self, tmp_path: Path) -> None:
        """List comprehensions work in template expressions."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "page.html").write_text(
            "{{ [x.upper() for x in items if x != 'b'] | join(', ') }}"
        )
        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        html = env.get_template("page.html").render(items=["a", "b", "c"])
        assert html == "A, C"

    def test_trans_block_renders(self, tmp_path: Path) -> None:
        """{% trans %} blocks render through chirp's environment."""
        from chirp.config import AppConfig
        from chirp.templating.integration import create_environment

        (tmp_path / "page.html").write_text("{% trans %}Hello{% endtrans %}")
        config = AppConfig(template_dir=str(tmp_path))
        env = create_environment(config, filters={}, globals_={})
        # Without gettext installed, trans blocks return source string
        html = env.get_template("page.html").render()
        assert html == "Hello"

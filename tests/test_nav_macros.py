"""Tests for chirp nav link template macros.

Renders the nav_link macro with a kida Environment backed by PackageLoader
and verifies the HTML output includes hx-swap for view transitions.
"""

from kida import Environment, PackageLoader

from chirp.templating.filters import BUILTIN_FILTERS


def _make_env() -> Environment:
    """Create a kida env that can load chirp nav macros."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    return env


def _render(env: Environment, source: str, **ctx: object) -> str:
    """Render a template string that imports chirp nav macros."""
    tpl = env.from_string(source)
    return tpl.render(ctx).strip()


class TestNavLink:
    def test_basic_render(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/nav.html" import nav_link %}'
            '{{ nav_link("/story/123", "Story title") }}',
        )
        assert 'href="/story/123"' in html
        assert "Story title" in html
        assert 'hx-swap="innerHTML transition:true"' in html

    def test_with_class(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/nav.html" import nav_link %}'
            '{{ nav_link("/", "← Back", class="back") }}',
        )
        assert 'href="/"' in html
        assert 'class="back"' in html
        assert "← Back" in html

    def test_without_class_no_empty_attribute(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/nav.html" import nav_link %}'
            '{{ nav_link("/home", "Home") }}',
        )
        assert 'href="/home"' in html
        assert 'class=""' not in html

    def test_push_url(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/nav.html" import nav_link %}'
            '{{ nav_link("/story/1", "Story", push_url=true) }}',
        )
        assert 'hx-push-url="true"' in html

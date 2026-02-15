"""Tests for chirp boost layout template.

Verifies the boost layout loads and renders with correct structure
for htmx-boost, SSE, and view transitions.
"""

from kida import Environment, PackageLoader

from chirp.templating.filters import BUILTIN_FILTERS


def _make_env() -> Environment:
    """Create a kida env that can load chirp layouts."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    return env


class TestBoostLayout:
    def test_layout_loads_and_renders(self) -> None:
        env = _make_env()
        tpl = env.get_template("chirp/layouts/boost.html")
        html = tpl.render({"content": "Hello"}).strip()
        assert 'id="main"' in html
        assert 'hx-boost="true"' in html
        assert 'hx-target="#main"' in html
        assert 'hx-swap="innerHTML"' in html
        # Container must NOT have transition:true (only nav links do)
        assert 'hx-swap="innerHTML"' in html
        main_swap = html[html.find('id="main"'): html.find('id="main"') + 80]
        assert "transition:true" not in main_swap
        assert 'meta name="view-transition"' in html
        assert "htmx.org" in html
        assert "htmx-ext-sse" in html
        assert ".sse-sink" in html

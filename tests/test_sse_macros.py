"""Tests for chirp SSE template macros.

Renders the sse_scope macro with a kida Environment backed by PackageLoader
and verifies the HTML output includes hx-disinherit and hx-target.
"""

from kida import Environment, PackageLoader

from chirp.templating.filters import BUILTIN_FILTERS


def _make_env() -> Environment:
    """Create a kida env that can load chirp SSE macros."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    return env


def _render(env: Environment, source: str, **ctx: object) -> str:
    """Render a template string that imports chirp SSE macros."""
    tpl = env.from_string(source)
    return tpl.render(ctx).strip()


class TestSseScope:
    def test_basic_render(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/sse.html" import sse_scope %}'
            '{{ sse_scope("/events") }}',
        )
        assert 'sse-connect="/events"' in html
        assert "hx-disinherit" in html
        assert "hx-target" in html
        assert 'sse-swap="fragment"' in html
        assert "sse-sink" in html

    def test_with_options(self) -> None:
        env = _make_env()
        html = _render(
            env,
            '{% from "chirp/sse.html" import sse_scope %}'
            '{{ sse_scope("/stream", swap="status", wrapper_class="my-sse") }}',
        )
        assert 'sse-connect="/stream"' in html
        assert 'sse-swap="status"' in html
        assert "my-sse" in html

"""Tests for chirp SSE template macros.

Renders the sse_scope macro with a kida Environment backed by PackageLoader
and verifies the HTML output includes hx-disinherit and hx-target.
"""

import pytest
from kida import Environment, PackageLoader
from kida.exceptions import TemplateRuntimeError

from chirp.realtime.sse import _validate_htmx4_sse_target
from chirp.templating.filters import BUILTIN_FILTERS


def _make_env(*, tier: str = "2-managed") -> Environment:
    """Create a kida env that can load chirp SSE macros."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    env.add_global("__chirp_htmx_tier__", tier)
    env.add_global("__chirp_sse_target__", _validate_htmx4_sse_target)
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
            '{% from "chirp/sse.html" import sse_scope %}{{ sse_scope("/events") }}',
        )
        assert 'sse-connect="/events"' in html
        assert "hx-disinherit" in html
        assert "hx-target" in html
        assert 'sse-swap="message"' in html
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

    def test_htmx4_render_uses_native_connection_and_explicit_target(self) -> None:
        env = _make_env(tier="4-preview")
        html = _render(
            env,
            '{% from "chirp/sse.html" import sse_scope %}'
            '{{ sse_scope("/stream", swap="status", wrapper_class="my-sse") }}',
        )
        assert 'hx-sse:connect="/stream"' in html
        assert 'hx-target="#status"' in html
        assert 'id="status"' in html
        assert "my-sse" in html
        assert "sse-connect" not in html
        assert "sse-swap" not in html
        assert "hx-disinherit" not in html

    def test_htmx4_render_rejects_selector_unsafe_target(self) -> None:
        env = _make_env(tier="4-preview")
        with pytest.raises(TemplateRuntimeError, match="safe htmx 4 DOM id"):
            _render(
                env,
                '{% from "chirp/sse.html" import sse_scope %}'
                '{{ sse_scope("/stream", swap="status panel") }}',
            )

"""Tests for Suspense-style streaming HTML.

Covers:

- Sync-only fallback (no awaitables — full page in one chunk)
- Async deferral (awaitable values deferred, shell shows skeletons)
- htmx OOB swap output format
- ``<template>`` + ``<script>`` fallback for non-htmx loads
- Mixed sync/async context
- Error mid-stream (deferred resolution failure)
- defer_map override for block-to-DOM-ID mapping
- Suspense dataclass construction
"""

import asyncio

import pytest
from kida import DictLoader, Environment

from chirp.templating.returns import Suspense
from chirp.templating.suspense import (
    format_oob_htmx,
    format_oob_script,
    render_suspense,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = """\
<html>
<body>
<h1>{{ title }}</h1>
<div id="stats">
{% block stats %}
  {% if stats %}
    <ul>{% for s in stats %}<li>{{ s }}</li>{% end %}</ul>
  {% else %}
    <div class="skeleton">Loading stats...</div>
  {% end %}
{% end %}
</div>
<div id="feed">
{% block feed %}
  {% if feed %}
    <ul>{% for f in feed %}<li>{{ f }}</li>{% end %}</ul>
  {% else %}
    <div class="skeleton">Loading feed...</div>
  {% end %}
{% end %}
</div>
</body>
</html>"""

_SIMPLE_TEMPLATE = """\
<div id="content">
{% block content %}
  {% if data %}
    <p>{{ data }}</p>
  {% else %}
    <p class="loading">Loading...</p>
  {% end %}
{% end %}
</div>"""


def _env() -> Environment:
    """Build a kida Environment with in-memory test templates."""
    return Environment(
        loader=DictLoader(
            {
                "dashboard.html": _DASHBOARD_TEMPLATE,
                "simple.html": _SIMPLE_TEMPLATE,
            }
        )
    )


async def _collect_chunks(
    env: Environment,
    suspense: Suspense,
    *,
    is_htmx: bool = False,
) -> list[str]:
    """Collect all chunks from render_suspense into a list."""
    return [c async for c in render_suspense(env, suspense, is_htmx=is_htmx)]


async def _delayed_value(value: object, delay: float = 0.01) -> object:
    """Return *value* after a short delay (simulates async data fetch)."""
    await asyncio.sleep(delay)
    return value


# ---------------------------------------------------------------------------
# Suspense dataclass
# ---------------------------------------------------------------------------


class TestSuspenseDataclass:
    """Construction and field access."""

    def test_basic_construction(self):
        s = Suspense("page.html", title="Home", items=[1, 2])
        assert s.template_name == "page.html"
        assert s.context == {"title": "Home", "items": [1, 2]}
        assert s.defer_map == {}

    def test_with_defer_map(self):
        s = Suspense("page.html", defer_map={"stats": "stats-panel"}, title="X")
        assert s.defer_map == {"stats": "stats-panel"}
        assert s.context == {"title": "X"}

    def test_frozen(self):
        s = Suspense("page.html", title="Home")
        try:
            s.template_name = "other.html"
            pytest.fail("Should have raised")
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# OOB formatters
# ---------------------------------------------------------------------------


class TestFormatOOBHtmx:
    """htmx OOB swap wrapper."""

    def test_basic(self):
        html = format_oob_htmx("<p>Hello</p>", "stats")
        assert html == '<div id="stats" hx-swap-oob="true"><p>Hello</p></div>'

    def test_preserves_inner_html(self):
        inner = "<ul><li>a</li><li>b</li></ul>"
        html = format_oob_htmx(inner, "feed")
        assert inner in html
        assert 'id="feed"' in html


class TestFormatOOBScript:
    """``<template>`` + ``<script>`` fallback."""

    def test_contains_template_and_script(self):
        html = format_oob_script("<p>Data</p>", "stats")
        assert "<template" in html
        assert "<script>" in html
        assert "_chirp_d_stats" in html
        assert "<p>Data</p>" in html

    def test_targets_correct_element(self):
        html = format_oob_script("<p>X</p>", "my-panel")
        assert 'getElementById("my-panel")' in html


# ---------------------------------------------------------------------------
# Sync-only fallback
# ---------------------------------------------------------------------------


class TestSyncOnlyFallback:
    """No awaitables — renders full page in a single chunk."""

    async def test_single_chunk(self):
        env = _env()
        s = Suspense("dashboard.html", title="Dashboard", stats=["a", "b"], feed=["x"])
        chunks = await _collect_chunks(env, s)

        assert len(chunks) == 1
        assert "<h1>Dashboard</h1>" in chunks[0]
        assert "<li>a</li>" in chunks[0]
        assert "<li>x</li>" in chunks[0]
        assert "skeleton" not in chunks[0]

    async def test_no_oob_when_sync(self):
        env = _env()
        s = Suspense("dashboard.html", title="Test", stats=["s"], feed=["f"])
        chunks = await _collect_chunks(env, s, is_htmx=True)

        assert len(chunks) == 1
        assert "hx-swap-oob" not in chunks[0]


# ---------------------------------------------------------------------------
# Async deferral
# ---------------------------------------------------------------------------


class TestAsyncDeferral:
    """Awaitable values are deferred — shell shows skeletons."""

    async def test_shell_has_skeletons(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_delayed_value(["a", "b"]),
            feed=_delayed_value(["x", "y"]),
        )
        chunks = await _collect_chunks(env, s)

        # First chunk is the shell with skeletons
        shell = chunks[0]
        assert "<h1>Dashboard</h1>" in shell
        assert "Loading stats..." in shell
        assert "Loading feed..." in shell
        assert "<li>a</li>" not in shell

    async def test_oob_chunks_contain_real_data(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_delayed_value(["a", "b"]),
            feed=_delayed_value(["x", "y"]),
        )
        chunks = await _collect_chunks(env, s)

        # Should have shell + at least one OOB chunk
        assert len(chunks) >= 2
        oob_combined = "".join(chunks[1:])
        assert "<li>a</li>" in oob_combined
        assert "<li>x</li>" in oob_combined

    async def test_htmx_oob_format(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_delayed_value(["a"]),
            feed=_delayed_value(["x"]),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob_combined = "".join(chunks[1:])
        assert 'hx-swap-oob="true"' in oob_combined

    async def test_script_fallback_format(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_delayed_value(["a"]),
            feed=_delayed_value(["x"]),
        )
        chunks = await _collect_chunks(env, s, is_htmx=False)

        oob_combined = "".join(chunks[1:])
        assert "<template" in oob_combined
        assert "<script>" in oob_combined


# ---------------------------------------------------------------------------
# Mixed sync/async
# ---------------------------------------------------------------------------


class TestMixedSyncAsync:
    """Some context values sync, some async."""

    async def test_sync_values_in_shell(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=["sync-stat"],  # sync
            feed=_delayed_value(["async-item"]),  # async
        )
        chunks = await _collect_chunks(env, s)

        shell = chunks[0]
        # Sync value should be rendered in the shell
        assert "<li>sync-stat</li>" in shell
        # Async value should be skeleton in the shell
        assert "Loading feed..." in shell

    async def test_only_deferred_blocks_in_oob(self):
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=["sync-stat"],  # sync
            feed=_delayed_value(["async-item"]),  # async
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob_combined = "".join(chunks[1:])
        # Only the feed block should appear in OOB (stats was sync)
        assert "<li>async-item</li>" in oob_combined
        # The stats block should NOT be re-rendered via OOB
        assert "sync-stat" not in oob_combined


# ---------------------------------------------------------------------------
# Error mid-stream
# ---------------------------------------------------------------------------


class TestErrorMidStream:
    """Errors during deferred resolution don't crash the stream."""

    async def test_resolution_error_yields_comment(self):
        async def _fail():
            raise ValueError("database down")

        env = _env()
        s = Suspense(
            "simple.html",
            data=_fail(),
        )
        chunks = await _collect_chunks(env, s)

        # Shell should still be sent
        assert len(chunks) >= 1
        assert "Loading..." in chunks[0]

        # Error comment should appear
        combined = "".join(chunks)
        assert "chirp:suspense error" in combined


# ---------------------------------------------------------------------------
# defer_map override
# ---------------------------------------------------------------------------


class TestDeferMap:
    """Custom block-to-DOM-ID mapping."""

    async def test_htmx_uses_defer_map(self):
        env = _env()
        s = Suspense(
            "simple.html",
            defer_map={"content": "main-panel"},
            data=_delayed_value("hello"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob_combined = "".join(chunks[1:])
        assert 'id="main-panel"' in oob_combined

    async def test_script_uses_defer_map(self):
        env = _env()
        s = Suspense(
            "simple.html",
            defer_map={"content": "main-panel"},
            data=_delayed_value("hello"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=False)

        oob_combined = "".join(chunks[1:])
        assert "_chirp_d_main-panel" in oob_combined
        assert 'getElementById("main-panel")' in oob_combined

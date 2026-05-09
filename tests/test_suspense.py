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
- Two blocks sharing one deferred key
- Ancestor block pruning
- Explicit defer_blocks bypass
"""

import asyncio
import inspect

import pytest
from kida import DictLoader, Environment

from chirp.cache import DeferredCache
from chirp.templating.returns import Suspense
from chirp.templating.suspense import (
    CHIRP_DEFER_PENDING_KEY,
    DEFERRED,
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
  {% if stats is deferred %}
    <div class="skeleton">Loading stats...</div>
  {% else %}
    <ul>{% for s in stats %}<li>{{ s }}</li>{% end %}</ul>
  {% end %}
{% end %}
</div>
<div id="feed">
{% block feed %}
  {% if feed is deferred %}
    <div class="skeleton">Loading feed...</div>
  {% else %}
    <ul>{% for f in feed %}<li>{{ f }}</li>{% end %}</ul>
  {% end %}
{% end %}
</div>
</body>
</html>"""

_DEFER_PENDING_TEMPLATE = """\
<html><body>
{% block stats %}
<div id="stats">
{# Reference `stats` so block_metadata depends_on includes it (OOB discovery). #}
{% if stats is deferred %}
<span class="pending-flag">pending</span>
{% elif "stats" in __chirp_defer_pending__ %}
<span class="pending-flag">pending</span>
{% else %}
<span class="ready-flag">ready</span>
{% endif %}
</div>
{% end %}
</body></html>"""

_SIMPLE_TEMPLATE = """\
<div id="content">
{% block content %}
  {% if data is deferred %}
    <p class="loading">Loading...</p>
  {% else %}
    <p>{{ data }}</p>
  {% end %}
{% end %}
</div>"""

_SHARED_KEY_TEMPLATE = """\
<html><body>
{% block page_content %}
<h1>{{ title }}</h1>
<div id="hero_stars">
{% block hero_stars %}
  {% if stars is deferred %}
    <span class="skeleton">…</span>
  {% else %}
    <span>{{ stars }} stars</span>
  {% end %}
{% end %}
</div>
<div id="footer_stars">
{% block footer_stars %}
  {% if stars is deferred %}
    <span class="skeleton">…</span>
  {% else %}
    <span>{{ stars }} stars</span>
  {% end %}
{% end %}
</div>
{% end %}
</body></html>"""

_TWO_CONSUMER_TEMPLATE = """\
<html><body>
<div id="hero">
{% block hero %}
  {% if hero is deferred %}
    <span class="skeleton">Loading hero...</span>
  {% else %}
    <span>{{ hero }}</span>
  {% end %}
{% end %}
</div>
<div id="footer">
{% block footer %}
  {% if footer is deferred %}
    <span class="skeleton">Loading footer...</span>
  {% else %}
    <span>{{ footer }}</span>
  {% end %}
{% end %}
</div>
</body></html>"""


def _env() -> Environment:
    """Build a kida Environment with in-memory test templates."""
    env = Environment(
        loader=DictLoader(
            {
                "dashboard.html": _DASHBOARD_TEMPLATE,
                "defer_pending.html": _DEFER_PENDING_TEMPLATE,
                "simple.html": _SIMPLE_TEMPLATE,
                "shared_key.html": _SHARED_KEY_TEMPLATE,
                "two_consumer.html": _TWO_CONSUMER_TEMPLATE,
            }
        )
    )
    _register_deferred_test(env)
    return env


def _register_deferred_test(env: Environment) -> None:
    """Register the ``deferred`` kida test on an environment."""
    env.add_test("deferred", lambda val: val is DEFERRED)


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


async def _resolve_deferred(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
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
    """Errors during deferred resolution produce visible error indicators."""

    async def test_resolution_error_yields_visible_error(self):
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

        # Visible error indicator should replace the skeleton
        combined = "".join(chunks)
        assert "chirp-suspense-error" in combined
        assert "Error loading data" in combined

    async def test_resolution_error_htmx_targets_pending_keys(self):
        async def _fail():
            raise ValueError("database down")

        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_fail(),
            feed=_fail(),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        # Shell + error OOB chunks for each pending key
        assert len(chunks) >= 2
        oob = "".join(chunks[1:])
        assert "chirp-suspense-error" in oob
        assert 'hx-swap-oob="true"' in oob

    async def test_custom_error_block_renders_fallback(self):
        """Per-route error_block renders custom error HTML from a template."""

        async def _fail():
            raise ValueError("database down")

        error_tmpl = (
            "{% block fallback %}"
            '<div class="custom-error">Oops: {{ block_name }}</div>'
            "{% endblock %}"
        )
        env = Environment(
            loader=DictLoader(
                {
                    "simple.html": _SIMPLE_TEMPLATE,
                    "errors/deferred.html": error_tmpl,
                }
            )
        )
        _register_deferred_test(env)

        s = Suspense("simple.html", error_block="fallback", data=_fail())
        chunks = [
            c
            async for c in render_suspense(
                env,
                s,
                is_htmx=False,
                error_template="errors/deferred.html",
                error_block="fallback",
            )
        ]

        combined = "".join(chunks)
        assert "custom-error" in combined
        assert "Oops: data" in combined
        # Should NOT contain the default hardcoded error
        assert "chirp-suspense-error" not in combined


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


# ---------------------------------------------------------------------------
# Layout wrapping
# ---------------------------------------------------------------------------


class TestLayoutWrapping:
    """render_suspense with layout_chain wraps shell in layout shell."""

    async def test_layout_chain_wraps_shell(self):
        from chirp.pages.types import LayoutChain, LayoutInfo

        layout_html = """<!DOCTYPE html><html><head><title>{{ title }}</title></head>
<body><div id="body">{% block content %}{% end %}</div></body></html>"""

        env = Environment(
            loader=DictLoader(
                {
                    "dashboard.html": _DASHBOARD_TEMPLATE,
                    "_layout.html": layout_html,
                }
            )
        )
        _register_deferred_test(env)
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))

        s = Suspense("dashboard.html", title="Dashboard", stats=["a"], feed=["x"])
        chunks = [
            c
            async for c in render_suspense(
                env,
                s,
                layout_chain=chain,
                layout_context={"title": "Dashboard"},
            )
        ]

        assert len(chunks) == 1
        assert "<!DOCTYPE html>" in chunks[0]
        assert "<title>Dashboard</title>" in chunks[0]
        assert 'id="body"' in chunks[0]
        assert "<h1>Dashboard</h1>" in chunks[0]

    async def test_no_layout_when_layout_chain_none(self):
        env = _env()
        s = Suspense("dashboard.html", title="X", stats=["a"], feed=["x"])
        chunks = [c async for c in render_suspense(env, s, layout_chain=None)]

        assert len(chunks) == 1
        assert "<!DOCTYPE html>" not in chunks[0]  # no layout shell
        assert "<h1>X</h1>" in chunks[0]

    async def test_fragment_request_skips_layout_wrapping(self):
        from chirp.pages.types import LayoutChain, LayoutInfo

        env = _env()
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))
        request = type(
            "Req",
            (),
            {
                "is_fragment": True,
                "is_htmx": True,
                "is_narrow_fragment": True,
                "is_boosted": False,
                "is_history_restore": False,
                "htmx_target": None,
            },
        )()

        s = Suspense("dashboard.html", title="X", stats=["a"], feed=["x"])
        chunks = [
            c
            async for c in render_suspense(
                env,
                s,
                layout_chain=chain,
                layout_context={},
                request=request,
            )
        ]

        # Fragment request → no layout wrapping
        assert len(chunks) == 1
        assert "<!DOCTYPE html>" not in chunks[0]
        assert "<h1>X</h1>" in chunks[0]

    async def test_boosted_replace_outlet_skips_layout_wrapping(self):
        from chirp.pages.types import LayoutChain, LayoutInfo

        layout_html = """<!DOCTYPE html><html><head><title>{{ title }}</title></head>
<body><div id="site-content">{% block content %}{% end %}</div></body></html>"""
        env = Environment(
            loader=DictLoader(
                {
                    "dashboard.html": _DASHBOARD_TEMPLATE,
                    "_layout.html": layout_html,
                }
            )
        )
        _register_deferred_test(env)
        chain = LayoutChain(
            layouts=(
                LayoutInfo(
                    "_layout.html",
                    "body",
                    0,
                    outlet_target_id="site-content",
                    outlet_mode="replace",
                ),
            )
        )
        request = type(
            "Req",
            (),
            {
                "is_fragment": True,
                "is_htmx": True,
                "is_narrow_fragment": False,
                "is_history_restore": False,
                "is_boosted": True,
                "htmx_target": "site-content",
            },
        )()

        s = Suspense("dashboard.html", title="X", stats=["a"], feed=["x"])
        chunks = [
            c
            async for c in render_suspense(
                env,
                s,
                layout_chain=chain,
                layout_context={"title": "X"},
                request=request,
            )
        ]

        assert len(chunks) == 1
        assert "<!DOCTYPE html>" not in chunks[0]
        assert 'id="site-content"' not in chunks[0]
        assert "<h1>X</h1>" in chunks[0]

    async def test_boosted_replace_outlet_preserves_descendant_layouts(self):
        from chirp.pages.types import LayoutChain, LayoutInfo

        env = Environment(
            loader=DictLoader(
                {
                    "dashboard.html": _DASHBOARD_TEMPLATE,
                    "_layout.html": (
                        "<!DOCTYPE html><html><body>"
                        '<div id="site-content">{% block content %}{% end %}</div>'
                        "</body></html>"
                    ),
                    "_showcase.html": '<main id="main">{% block content %}{% end %}</main>',
                }
            )
        )
        _register_deferred_test(env)
        chain = LayoutChain(
            layouts=(
                LayoutInfo(
                    "_layout.html",
                    "body",
                    0,
                    outlet_target_id="site-content",
                    outlet_mode="replace",
                ),
                LayoutInfo("_showcase.html", "site-content", 1),
            )
        )
        request = type(
            "Req",
            (),
            {
                "is_fragment": True,
                "is_htmx": True,
                "is_narrow_fragment": False,
                "is_history_restore": False,
                "is_boosted": True,
                "htmx_target": "site-content",
            },
        )()

        s = Suspense("dashboard.html", title="X", stats=["a"], feed=["x"])
        chunks = [
            c
            async for c in render_suspense(
                env,
                s,
                layout_chain=chain,
                layout_context={"title": "X"},
                request=request,
            )
        ]

        assert len(chunks) == 1
        assert "<!DOCTYPE html>" not in chunks[0]
        assert 'id="site-content"' not in chunks[0]
        assert 'id="main"' in chunks[0]
        assert "<h1>X</h1>" in chunks[0]


# ---------------------------------------------------------------------------
# Two blocks sharing one deferred key
# ---------------------------------------------------------------------------


class TestSharedDeferredKey:
    """Multiple blocks that depend on the same awaitable context value."""

    async def test_both_leaf_blocks_receive_oob(self):
        env = _env()
        s = Suspense(
            "shared_key.html",
            title="Repo",
            stars=_delayed_value("42"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        shell = chunks[0]
        assert "skeleton" in shell
        assert "42 stars" not in shell

        oob = "".join(chunks[1:])
        assert 'id="hero_stars"' in oob
        assert 'id="footer_stars"' in oob
        assert oob.count("42 stars") == 2

    async def test_parent_block_pruned_from_oob(self):
        """page_content depends on 'stars' too, but should be pruned."""
        env = _env()
        s = Suspense(
            "shared_key.html",
            title="Repo",
            stars=_delayed_value("7"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob = "".join(chunks[1:])
        assert 'id="page_content"' not in oob

    async def test_script_fallback_both_blocks(self):
        env = _env()
        s = Suspense(
            "shared_key.html",
            title="Repo",
            stars=_delayed_value("99"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=False)

        oob = "".join(chunks[1:])
        assert "_chirp_d_hero_stars" in oob
        assert "_chirp_d_footer_stars" in oob
        assert oob.count("99 stars") == 2


# ---------------------------------------------------------------------------
# Explicit defer_blocks bypass
# ---------------------------------------------------------------------------


class TestDeferBlocks:
    """Suspense.defer_blocks overrides static analysis."""

    def test_dataclass_accepts_defer_blocks(self):
        s = Suspense("page.html", defer_blocks=("a", "b"), data="x")
        assert s.defer_blocks == ("a", "b")

    def test_dataclass_default_none(self):
        s = Suspense("page.html", data="x")
        assert s.defer_blocks is None

    async def test_explicit_blocks_rendered(self):
        env = _env()
        s = Suspense(
            "shared_key.html",
            defer_blocks=("footer_stars",),
            title="Repo",
            stars=_delayed_value("55"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob = "".join(chunks[1:])
        assert 'id="footer_stars"' in oob
        assert 'id="hero_stars"' not in oob

    async def test_explicit_blocks_skip_static_analysis(self):
        """When defer_blocks is set, only those blocks are rendered."""
        env = _env()
        s = Suspense(
            "shared_key.html",
            defer_blocks=("hero_stars",),
            title="Repo",
            stars=_delayed_value("11"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob = "".join(chunks[1:])
        assert 'id="hero_stars"' in oob
        assert oob.count("11 stars") == 1

    async def test_empty_defer_blocks_produces_no_oob(self):
        """defer_blocks=() means no blocks are re-rendered — only the shell."""
        env = _env()
        s = Suspense(
            "shared_key.html",
            defer_blocks=(),
            title="Repo",
            stars=_delayed_value("77"),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        assert len(chunks) == 1
        assert "skeleton" in chunks[0]
        assert "77 stars" not in chunks[0]

    async def test_unknown_defer_blocks_raises(self):
        """defer_blocks with nonexistent block names always raises ConfigurationError."""
        from chirp.errors import ConfigurationError

        env = Environment(
            loader=DictLoader({"shared_key.html": _SHARED_KEY_TEMPLATE}),
            auto_reload=False,
        )
        _register_deferred_test(env)
        stars = _delayed_value("33")
        s = Suspense(
            "shared_key.html",
            defer_blocks=("hero_stars", "nonexistent_block"),
            title="Repo",
            stars=stars,
        )
        try:
            with pytest.raises(ConfigurationError, match="nonexistent_block"):
                await _collect_chunks(env, s, is_htmx=True)
        finally:
            stars.close()

    async def test_unknown_defer_blocks_raises_in_debug(self):
        """In debug mode (auto_reload), unknown defer_blocks also raises ConfigurationError."""
        from chirp.errors import ConfigurationError

        env = Environment(
            loader=DictLoader({"shared_key.html": _SHARED_KEY_TEMPLATE}),
            auto_reload=True,
        )
        _register_deferred_test(env)
        stars = _delayed_value("33")
        s = Suspense(
            "shared_key.html",
            defer_blocks=("hero_stars", "nonexistent_block"),
            title="Repo",
            stars=stars,
        )
        try:
            with pytest.raises(ConfigurationError, match="nonexistent_block"):
                await _collect_chunks(env, s, is_htmx=True)
        finally:
            stars.close()

    async def test_unknown_defer_blocks_suggests_close_match(self):
        """Error message includes 'did you mean' suggestion for close block names."""
        from chirp.errors import ConfigurationError

        env = Environment(
            loader=DictLoader({"shared_key.html": _SHARED_KEY_TEMPLATE}),
            auto_reload=False,
        )
        _register_deferred_test(env)
        stars = _delayed_value("33")
        s = Suspense(
            "shared_key.html",
            defer_blocks=("hero_star",),  # close to "hero_stars"
            title="Repo",
            stars=stars,
        )
        try:
            with pytest.raises(ConfigurationError, match="did you mean 'hero_stars'"):
                await _collect_chunks(env, s, is_htmx=True)
        finally:
            stars.close()


# ---------------------------------------------------------------------------
# Empty block discovery warning
# ---------------------------------------------------------------------------


class TestEmptyDiscoveryError:
    """Auto-discovery that finds zero blocks should raise."""

    async def test_empty_discovery_raises(self):
        """When deferred keys exist but no blocks depend on them, raise ConfigurationError."""
        from chirp.errors import ConfigurationError

        # Template with a block that doesn't reference the deferred key
        no_dep_template = """\
<html><body>
{% block content %}
<p>Static content only</p>
{% end %}
</body></html>"""

        env = Environment(loader=DictLoader({"nodep.html": no_dep_template}))
        _register_deferred_test(env)
        s = Suspense(
            "nodep.html",
            data=_delayed_value("hello"),
        )
        with pytest.raises(ConfigurationError, match="no blocks discovered"):
            await _collect_chunks(env, s, is_htmx=True)


# ---------------------------------------------------------------------------
# Visible block render errors
# ---------------------------------------------------------------------------


class TestBlockRenderError:
    """Render errors in deferred blocks produce visible error indicators."""

    async def test_block_render_error_htmx(self):
        """Block render error sends visible OOB error instead of HTML comment."""
        # Template where block references a variable that will cause an error
        error_template = """\
<html><body>
{% block stats %}
  {% if stats is deferred %}
    <div class="skeleton">Loading...</div>
  {% else %}
    {{ stats.nonexistent_method() }}
  {% end %}
{% end %}
</body></html>"""

        env = Environment(loader=DictLoader({"error.html": error_template}))
        _register_deferred_test(env)
        s = Suspense(
            "error.html",
            defer_blocks=("stats",),
            stats=_delayed_value({"value": 42}),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)

        oob = "".join(chunks[1:])
        # Visible error, not HTML comment
        assert "chirp-suspense-error" in oob
        assert "<!-- chirp:suspense" not in oob
        assert 'hx-swap-oob="true"' in oob

    async def test_block_render_error_script(self):
        """Block render error in script mode sends visible error via template+script."""
        error_template = """\
<html><body>
{% block stats %}
  {% if stats is deferred %}
    <div class="skeleton">Loading...</div>
  {% else %}
    {{ stats.nonexistent_method() }}
  {% end %}
{% end %}
</body></html>"""

        env = Environment(loader=DictLoader({"error.html": error_template}))
        _register_deferred_test(env)
        s = Suspense(
            "error.html",
            defer_blocks=("stats",),
            stats=_delayed_value({"value": 42}),
        )
        chunks = await _collect_chunks(env, s, is_htmx=False)

        oob = "".join(chunks[1:])
        assert "chirp-suspense-error" in oob
        assert "<template" in oob
        assert "<script>" in oob


# ---------------------------------------------------------------------------
# __chirp_defer_pending__ context key
# ---------------------------------------------------------------------------


class TestDeferPendingKey:
    """CHIRP_DEFER_PENDING_KEY / __chirp_defer_pending__ in shell vs OOB."""

    def test_constant_value(self) -> None:
        assert CHIRP_DEFER_PENDING_KEY == "__chirp_defer_pending__"

    def test_chirp_lazy_export(self) -> None:
        import chirp

        assert chirp.CHIRP_DEFER_PENDING_KEY == "__chirp_defer_pending__"

    async def test_shell_lists_pending_keys(self) -> None:
        env = _env()
        s = Suspense(
            "defer_pending.html",
            stats=_delayed_value(["a"]),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)
        shell = chunks[0]
        assert "pending-flag" in shell
        assert "ready-flag" not in shell

    async def test_oob_block_sees_empty_pending(self) -> None:
        env = _env()
        s = Suspense(
            "defer_pending.html",
            stats=_delayed_value(["a"]),
        )
        chunks = await _collect_chunks(env, s, is_htmx=True)
        oob = "".join(chunks[1:])
        assert "ready-flag" in oob
        assert "pending-flag" not in oob

    async def test_sync_only_has_empty_pending(self) -> None:
        env = _env()
        s = Suspense("defer_pending.html", stats=["sync"])
        chunks = await _collect_chunks(env, s)
        assert len(chunks) == 1
        assert "ready-flag" in chunks[0]
        assert "pending-flag" not in chunks[0]

    async def test_resolved_empty_collections_leave_skeleton(self) -> None:
        """Empty tuple/list is not none after resolve — OOB must not re-show skeleton."""
        env = _env()
        s = Suspense(
            "dashboard.html",
            title="Dashboard",
            stats=_delayed_value([]),
            feed=_delayed_value([]),
        )
        chunks = await _collect_chunks(env, s)
        assert "Loading stats..." in chunks[0]
        oob = "".join(chunks[1:])
        assert "Loading stats..." not in oob
        assert "Loading feed..." not in oob


# ---------------------------------------------------------------------------
# DeferredCache integration
# ---------------------------------------------------------------------------


class TestDeferredCacheIntegration:
    """DeferredCache keeps Suspense behavior on cold and warm paths."""

    async def test_cold_miss_defers_then_warm_hit_renders_in_shell(self) -> None:
        cache = DeferredCache(default_ttl=60)
        calls = 0

        async def factory() -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return "42"

        env = _env()
        cold = Suspense(
            "shared_key.html",
            title="Home",
            stars=cache.get_or_defer("gh:repo", factory),
        )
        cold_chunks = await _collect_chunks(env, cold, is_htmx=True)

        assert "skeleton" in cold_chunks[0]
        assert 'hx-swap-oob="true"' in "".join(cold_chunks[1:])
        assert calls == 1

        warm = Suspense(
            "shared_key.html",
            title="Home",
            stars=cache.get_or_defer("gh:repo", factory),
        )
        warm_chunks = await _collect_chunks(env, warm, is_htmx=True)

        assert len(warm_chunks) == 1
        assert "42 stars" in warm_chunks[0]
        assert "skeleton" not in warm_chunks[0]
        assert "hx-swap-oob" not in warm_chunks[0]
        assert calls == 1

    async def test_two_cold_consumers_share_one_factory_call(self) -> None:
        cache = DeferredCache(default_ttl=60)
        calls = 0

        async def factory() -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return "shared value"

        env = _env()
        suspense = Suspense(
            "two_consumer.html",
            hero=cache.get_or_defer("shared", factory),
            footer=cache.get_or_defer("shared", factory),
        )
        chunks = await _collect_chunks(env, suspense, is_htmx=True)

        assert calls == 1
        assert "Loading hero" in chunks[0]
        assert "Loading footer" in chunks[0]
        oob = "".join(chunks[1:])
        assert oob.count("shared value") == 2

    @pytest.mark.parametrize("value", [0, "", None, []])
    async def test_cached_falsy_values_render_as_loaded(self, value: object) -> None:
        cache = DeferredCache(default_ttl=60)

        async def factory() -> object:
            return value

        env = _env()
        assert await _resolve_deferred(cache.get_or_defer("falsy", factory)) == value

        chunks = await _collect_chunks(
            env,
            Suspense("simple.html", data=cache.get_or_defer("falsy", factory)),
            is_htmx=True,
        )

        assert len(chunks) == 1
        assert "Loading..." not in chunks[0]

    async def test_factory_failure_uses_suspense_fallback_and_does_not_cache(self) -> None:
        cache = DeferredCache(default_ttl=60)
        calls = 0

        async def fail() -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("upstream down")

        env = _env()
        chunks = await _collect_chunks(
            env,
            Suspense("simple.html", data=cache.get_or_defer("fragile", fail)),
        )

        assert calls == 1
        combined = "".join(chunks)
        assert "Loading..." in chunks[0]
        assert "chirp-suspense-error" in combined

        async def recover() -> str:
            nonlocal calls
            calls += 1
            return "ok"

        assert await _resolve_deferred(cache.get_or_defer("fragile", recover)) == "ok"
        assert cache.get_or_defer("fragile", recover) == "ok"
        assert calls == 2

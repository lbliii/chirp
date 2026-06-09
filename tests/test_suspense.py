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
import time

import anyio
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


async def _drain_into(
    env: Environment,
    suspense: Suspense,
    sink: list[str],
    *,
    is_htmx: bool = False,
) -> None:
    """Drain render_suspense into *sink*, appending each chunk as it is yielded.

    Lets a test observe exactly which chunks were emitted before an exception
    raised mid-stream (e.g. asserting zero shell bytes preceded a discovery
    failure). Kept as a single awaitable so it fits a ``pytest.raises`` block.
    """
    # Incremental append (not a comprehension): we must retain whatever was
    # emitted if render_suspense raises mid-stream.
    async for chunk in render_suspense(env, suspense, is_htmx=is_htmx):
        sink.append(chunk)  # noqa: PERF401


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

    def test_no_nonce_attr_by_default(self):
        html = format_oob_script("<p>X</p>", "stats")
        assert "<script>" in html
        assert "nonce=" not in html

    def test_nonce_attr_when_provided(self):
        html = format_oob_script("<p>X</p>", "stats", nonce="abc123")
        assert '<script nonce="abc123">' in html


class TestSuspenseStreamCarriesLiveNonce:
    """Acceptance: framework inline scripts in a streamed Suspense response
    carry a *live* nonce — the #181 lifecycle fix.

    Drains a Suspense stream while the CSP nonce ContextVar is set (mirroring
    what ``send_streaming_response`` does from ``StreamingResponse.csp_nonce``)
    and asserts the streamed ``<script>`` chunks carry that non-empty nonce.
    """

    @pytest.mark.asyncio
    async def test_streamed_scripts_are_nonced(self):
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce

        env = _env()

        async def load_stats():
            return ["alice", "bob"]

        async def load_feed():
            return ["post"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())

        live_nonce = "LIVENONCE123"
        token = _set_csp_nonce(live_nonce)
        try:
            chunks = [chunk async for chunk in render_suspense(env, suspense, is_htmx=False)]
        finally:
            _reset_csp_nonce(token)

        body = "".join(chunks)
        # An inline <script> is emitted for the deferred block; it must carry
        # the live nonce, not an empty/dead one.
        assert "<script" in body
        assert f'<script nonce="{live_nonce}">' in body
        assert "<script>" not in body  # no un-nonced inline script slipped through

    @pytest.mark.asyncio
    async def test_streamed_scripts_unnonced_when_no_nonce(self):
        """With no nonce in scope the script is un-nonced (back-compat)."""
        env = _env()

        async def load_stats():
            return ["x", "y"]

        async def load_feed():
            return ["f"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())
        chunks = [chunk async for chunk in render_suspense(env, suspense, is_htmx=False)]
        body = "".join(chunks)
        assert "<script>" in body
        assert "nonce=" not in body


class TestSuspenseStreamNonceIntegration:
    """End-to-end #181 lifecycle: the integration path the bug actually lived in.

    Unlike :class:`TestSuspenseStreamCarriesLiveNonce` (which simulates the
    sender by calling ``_set_csp_nonce`` directly), this exercises the real
    chain:

    1. ``CSPNonceMiddleware`` runs, sets the nonce ContextVar, stamps the live
       nonce onto the ``StreamingResponse`` (``csp_nonce=``), then its ``finally``
       **resets the var the instant ``next()`` returns** — before any chunk is
       produced.
    2. ``send_streaming_response`` reads ``response.csp_nonce`` and re-establishes
       the var for the duration of the drain.
    3. ``render_suspense`` (the chunk generator) reads the *live* nonce at drain
       time and stamps it onto the framework inline ``<script>`` chunks.

    Without the stamp + re-establish, the generator would observe an empty nonce
    (the middleware already reset it) and emit a bare ``<script>`` blocked by a
    nonce-only CSP — the regression #181 fixes.
    """

    @pytest.mark.asyncio
    async def test_streamed_scripts_carry_live_nonce_end_to_end(self):
        from chirp.http.response import StreamingResponse
        from chirp.middleware.csp_nonce import CSPNonceMiddleware, csp_nonce
        from chirp.server.sender import send_streaming_response

        env = _env()

        async def load_stats():
            return ["alice", "bob"]

        async def load_feed():
            return ["post"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())

        # The handler builds the StreamingResponse whose chunks are the lazy
        # render_suspense generator. It is *not* iterated here, so the nonce is
        # read later — at drain time — exactly as in production.
        async def stream_next(request):
            return StreamingResponse(
                chunks=render_suspense(env, suspense, is_htmx=False),
                content_type="text/html",
            )

        # CSPNonceMiddleware never reads the request; a bare sentinel suffices.
        mw = CSPNonceMiddleware()
        response = await mw(object(), stream_next)
        assert isinstance(response, StreamingResponse)
        live_nonce = response.csp_nonce
        assert live_nonce, "middleware must stamp the live nonce onto the stream"

        # The middleware's finally has already reset the var: outside the drain
        # the nonce is gone. This is precisely the window the sender must cover.
        assert csp_nonce() == ""

        chunks: list[str] = []

        async def fake_send(message):
            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    chunks.append(body.decode("utf-8"))

        await send_streaming_response(response, fake_send)

        body = "".join(chunks)
        # Framework inline script(s) streamed for the deferred blocks must carry
        # the live nonce re-established by the sender — never a bare <script>.
        assert "<script" in body
        assert f'<script nonce="{live_nonce}">' in body
        assert "<script>" not in body  # no un-nonced inline script slipped through

        # The drain restored the pre-drain state: no nonce leaks past the stream.
        assert csp_nonce() == ""


class TestSuspenseAlpineNonceEndToEnd:
    """#195 integration: a real App returning a Suspense, driven through
    TestClient, emits BOTH a nonced Alpine ``safeData`` bootstrap AND a nonced
    Suspense OOB ``<script>``, both carrying the SAME nonce as the response CSP
    header.

    This is the end-to-end test the integration reviewer flagged as missing: it
    exercises the live chain (CSPNonceMiddleware sets the nonce + stamps the
    StreamingResponse, the sender re-establishes it during the drain,
    ``AlpineInject`` builds the bootstrap from the live nonce, and
    ``render_suspense`` stamps the OOB scripts) rather than any one layer in
    isolation.
    """

    @pytest.mark.asyncio
    async def test_alpine_and_suspense_scripts_share_response_nonce(self, tmp_path):
        import re

        from chirp import App
        from chirp.config import AppConfig
        from chirp.testing import TestClient

        # A full-page template with a deferred block so Suspense streams an OOB
        # <script> for the resolved block. Alpine injects its bootstrap before
        # </body>.
        (tmp_path / "dashboard.html").write_text(
            "<html><body>"
            "<h1>{{ title }}</h1>"
            '<div id="stats">'
            "{% block stats %}"
            "{% if stats is deferred %}<span class='skel'>…</span>"
            "{% else %}<ul>{% for s in stats %}<li>{{ s }}</li>{% end %}</ul>{% end %}"
            "{% end %}"
            "</div>"
            "</body></html>"
        )

        # csp_nonce_enabled auto-wires CSPNonceMiddleware at freeze; alpine=True
        # (non-CSP build) ships the inline safeData bootstrap.
        app = App(
            config=AppConfig(
                template_dir=tmp_path,
                alpine=True,
                csp_nonce_enabled=True,
            )
        )

        async def load_stats():
            return ["alice", "bob"]

        @app.route("/")
        def index():
            from chirp.templating.returns import Suspense

            return Suspense("dashboard.html", title="Dash", stats=load_stats())

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200

            csp = response.header("content-security-policy") or ""
            m = re.search(r"'nonce-([^']+)'", csp)
            assert m, f"no nonce in CSP header: {csp!r}"
            nonce = m.group(1)

            body = response.text

            # 1. The Alpine safeData bootstrap is nonced with the response nonce.
            assert "_chirpAlpineData" in body, "Alpine bootstrap not injected"
            alpine_start = body.rfind("<script", 0, body.index("_chirpAlpineData"))
            alpine_end = body.index("</script>", body.index("_chirpAlpineData"))
            alpine_script = body[alpine_start:alpine_end]
            assert f'nonce="{nonce}"' in alpine_script, (
                f"Alpine bootstrap missing live nonce; got: {alpine_script[:120]!r}"
            )

            # 2. The Suspense OOB <script> (resolved deferred block) is nonced
            #    with the SAME response nonce.
            assert "<li>alice</li>" in body, "deferred block did not resolve into the stream"
            assert f'<script nonce="{nonce}">' in body, "Suspense OOB script missing live nonce"

            # 3. No un-nonced inline <script> slipped through under the nonce CSP.
            assert "<script>" not in body


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

    async def test_empty_discovery_raises_before_any_shell_bytes(self):
        """The discovery error must raise BEFORE the shell is flushed (#145).

        Previously auto-discovery validated inside the generator AFTER the shell
        had already streamed, producing a half-rendered skeleton + a 500. The
        fix hoists discovery ahead of the first yield so the error is clean.
        """
        from chirp.errors import ConfigurationError

        no_dep_template = """\
<html><body>
{% block content %}
<p>Static content only</p>
{% end %}
</body></html>"""

        env = Environment(loader=DictLoader({"nodep.html": no_dep_template}))
        _register_deferred_test(env)
        s = Suspense("nodep.html", data=_delayed_value("hello"))

        chunks: list[str] = []
        with pytest.raises(ConfigurationError, match="no blocks discovered"):
            await _drain_into(env, s, chunks, is_htmx=True)
        # No shell bytes were emitted before the failure.
        assert chunks == []

    async def test_unknown_defer_blocks_raises_before_any_shell_bytes(self):
        """defer_blocks with an unknown name also fails before the shell flushes."""
        from chirp.errors import ConfigurationError

        template = """\
<html><body>
{% block stats %}{{ data }}{% end %}
</body></html>"""
        env = Environment(loader=DictLoader({"page.html": template}))
        _register_deferred_test(env)
        s = Suspense(
            "page.html",
            defer_blocks=("does_not_exist",),
            data=_delayed_value("hello"),
        )

        chunks: list[str] = []
        with pytest.raises(ConfigurationError, match="does_not_exist"):
            await _drain_into(env, s, chunks, is_htmx=True)
        assert chunks == []


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


# ---------------------------------------------------------------------------
# Off-loop rendering (issue #145 / #193): shell + deferred blocks render on a
# worker thread so a heavy Suspense render does not block concurrent requests.
#
# Mirrors the Stream off-loop concurrency probe in tests/test_streaming_html.py:
# a ticker coroutine counts how many times it advances during the render; if the
# render ran inline on the loop the ticker could not tick, so a high count proves
# the loop stayed free.
# ---------------------------------------------------------------------------

# Per-block CPU-bound work simulated by a blocking sleep inside a template global.
_SLOW_SHELL_TEMPLATE = """\
<html><body>
{% block content %}
  {% if data is deferred %}
    <p class="loading">{{ heavy() }}Loading...</p>
  {% else %}
    <p>{{ heavy() }}{{ data }}</p>
  {% end %}
{% end %}
</body></html>"""

# Template global reads the request ContextVar during render — proves the worker
# thread runs inside a copied contextvars.Context (the #181/#191 contract).
_REQ_GLOBAL_TEMPLATE = """\
<html><body>
{% block content %}
  {% if data is deferred %}
    <p class="loading">shell:{{ who() }}</p>
  {% else %}
    <p class="ready">block:{{ who() }}:{{ data }}</p>
  {% end %}
{% end %}
</body></html>"""


def _slow_suspense_env(sleep_s: float = 0.02) -> Environment:
    """Environment whose render blocks (simulates a CPU-bound Suspense render)."""
    env = Environment(loader=DictLoader({"slow.html": _SLOW_SHELL_TEMPLATE}))
    _register_deferred_test(env)

    def heavy() -> str:
        # Blocking sleep stands in for CPU-bound kida compilation. If this runs
        # inline on the loop, no concurrent task can advance for its duration.
        time.sleep(sleep_s)
        return ""

    env.add_global("heavy", heavy)
    return env


async def _count_ticks_during(coro_factory) -> tuple[list[str], int]:
    """Drain a Suspense stream while a ticker counts loop iterations.

    Returns (chunks, tick_count). A non-blocked loop ticks many times during the
    render; an inline-on-loop render would freeze the ticker at ~0.
    """
    counter = {"n": 0}

    async def ticker() -> None:
        while True:
            counter["n"] += 1
            await anyio.sleep(0.002)

    chunks: list[str] = []
    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        chunks = [chunk async for chunk in coro_factory()]
        tg.cancel_scope.cancel()
    return chunks, counter["n"]


# The blocking work lives in the *layout*, not the page template, so this probes
# the LayoutSuspense wrap render (render_with_layouts via _wrap_shell) — the
# production path #193 targets, distinct from the page-body render off-loop
# already covered by TestSuspenseOffLoop.
_HEAVY_LAYOUT_TEMPLATE = """\
{# target: body #}
<!DOCTYPE html><html><head><title>{{ title }}{{ heavy() }}</title></head>
<body><div id="body">{% block content %}{% end %}</div></body></html>"""

# Fast page template — all the slowness must come from the heavy layout wrap.
_LIGHT_PAGE_TEMPLATE = """\
<html><body>
{% block content %}
  {% if data is deferred %}
    <p class="loading">Loading...</p>
  {% else %}
    <p>{{ data }}</p>
  {% end %}
{% end %}
</body></html>"""


def _heavy_layout_env(sleep_s: float = 0.2) -> Environment:
    """Environment whose *layout* render blocks (CPU-bound layout wrap)."""
    env = Environment(
        loader=DictLoader(
            {
                "page.html": _LIGHT_PAGE_TEMPLATE,
                "_layout.html": _HEAVY_LAYOUT_TEMPLATE,
            }
        )
    )
    _register_deferred_test(env)

    def heavy() -> str:
        # Blocking sleep stands in for CPU-bound layout compilation. If the
        # layout wrap runs inline on the loop, no concurrent task advances.
        time.sleep(sleep_s)
        return ""

    env.add_global("heavy", heavy)
    return env


class TestSuspenseOffLoop:
    """A slow Suspense render must not block concurrent event-loop tasks."""

    @pytest.mark.asyncio
    async def test_slow_shell_render_does_not_block_loop(self) -> None:
        """The shell render (sync-only fast path) runs off the loop.

        The fast path renders the whole page in one ``template.render`` call; a
        heavy template there must not stall concurrent tasks.
        """
        env = _slow_suspense_env(sleep_s=0.2)
        # Sync-only context → fast-path single shell render.
        suspense = Suspense("slow.html", data="hello")

        chunks, ticks = await _count_ticks_during(
            lambda: render_suspense(env, suspense, is_htmx=True)
        )

        assert len(chunks) == 1
        assert "hello" in chunks[0]
        assert ticks > 10, f"loop appears blocked during shell render: ticks={ticks}"

    @pytest.mark.asyncio
    async def test_slow_deferred_block_render_does_not_block_loop(self) -> None:
        """The Phase-2 shell render AND the Phase-4 block render run off the loop.

        With a deferred awaitable the render path takes the shell + per-block OOB
        route. Both the shell and the deferred-block re-render call ``heavy()``,
        so the loop must stay free across both renders.
        """
        env = _slow_suspense_env(sleep_s=0.1)

        async def load() -> str:
            return "resolved"

        suspense = Suspense("slow.html", data=load())

        chunks, ticks = await _count_ticks_during(
            lambda: render_suspense(env, suspense, is_htmx=True)
        )

        # Shell + one OOB block chunk.
        assert len(chunks) == 2
        assert "loading" in chunks[0].lower()
        assert "resolved" in chunks[1]
        # Two heavy renders (~0.2s total) — a non-blocked loop ticks many times.
        assert ticks > 10, f"loop appears blocked during render: ticks={ticks}"


class TestLayoutSuspenseOffLoop:
    """The LayoutSuspense wrap render must not block the event loop (#193).

    Distinct from TestSuspenseOffLoop, which only exercises ``layout_chain=None``
    (no wrap). Here the blocking work lives in ``_layout.html`` so the probe fails
    if ``_wrap_shell`` runs ``render_with_layouts`` inline on the loop.
    """

    @pytest.mark.asyncio
    async def test_slow_layout_wrap_does_not_block_loop_fast_path(self) -> None:
        """The fast-path (sync-only) layout wrap runs off the loop.

        Sync-only context → fast-path single shell render + one ``_wrap_shell``
        call. The page body is trivial; the heavy work is the layout wrap.
        """
        from chirp.pages.types import LayoutChain, LayoutInfo

        env = _heavy_layout_env(sleep_s=0.2)
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))
        suspense = Suspense("page.html", data="hello")

        chunks, ticks = await _count_ticks_during(
            lambda: render_suspense(
                env,
                suspense,
                is_htmx=True,
                layout_chain=chain,
                layout_context={"title": "Dashboard"},
            )
        )

        assert len(chunks) == 1
        # Wrap actually happened (layout shell present, page body injected).
        assert "<!DOCTYPE html>" in chunks[0]
        assert "<p>hello</p>" in chunks[0]
        assert ticks > 10, f"loop appears blocked during layout wrap: ticks={ticks}"

    @pytest.mark.asyncio
    async def test_slow_layout_wrap_does_not_block_loop_deferred(self) -> None:
        """The Phase-2 shell wrap (deferred path) also runs off the loop.

        With a deferred awaitable the shell is wrapped in the heavy layout before
        the OOB block streams. The wrap must not stall concurrent tasks.
        """
        from chirp.pages.types import LayoutChain, LayoutInfo

        env = _heavy_layout_env(sleep_s=0.2)
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))

        async def load() -> str:
            return "resolved"

        suspense = Suspense("page.html", data=load())

        chunks, ticks = await _count_ticks_during(
            lambda: render_suspense(
                env,
                suspense,
                is_htmx=True,
                layout_chain=chain,
                layout_context={"title": "Dashboard"},
            )
        )

        # Shell (wrapped in layout) + one OOB block chunk.
        assert len(chunks) == 2
        assert "<!DOCTYPE html>" in chunks[0]
        assert "loading" in chunks[0].lower()
        assert "resolved" in chunks[1]
        assert ticks > 10, f"loop appears blocked during layout wrap: ticks={ticks}"


class TestSuspenseProgressiveFlush:
    """Shell-first + one OOB chunk per deferred block is preserved off-loop."""

    @pytest.mark.asyncio
    async def test_shell_first_then_one_chunk_per_block(self) -> None:
        env = _env()

        async def load_stats() -> list[str]:
            await asyncio.sleep(0.01)
            return ["a", "b"]

        async def load_feed() -> list[str]:
            await asyncio.sleep(0.02)
            return ["x"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())
        chunks = await _collect_chunks(env, suspense, is_htmx=True)

        # Shell first (skeletons, no real data), then exactly one OOB chunk per
        # deferred block — two blocks, two OOB chunks.
        assert len(chunks) == 3
        shell = chunks[0]
        assert "Loading stats..." in shell
        assert "Loading feed..." in shell
        assert "<li>a</li>" not in shell

        oob_chunks = chunks[1:]
        assert all('hx-swap-oob="true"' in c for c in oob_chunks)
        # Each block resolved into its own chunk.
        joined = "".join(oob_chunks)
        assert "<li>a</li>" in joined
        assert "<li>x</li>" in joined
        assert sum("<li>a</li>" in c for c in oob_chunks) == 1

    @pytest.mark.asyncio
    async def test_chunks_arrive_incrementally(self) -> None:
        """Shell arrives well before deferred blocks (not buffered then flushed)."""
        env = _env()

        async def load_stats() -> list[str]:
            await asyncio.sleep(0.05)
            return ["a"]

        async def load_feed() -> list[str]:
            await asyncio.sleep(0.05)
            return ["x"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())

        t0 = time.monotonic()
        arrival = [
            time.monotonic() - t0 async for _chunk in render_suspense(env, suspense, is_htmx=True)
        ]

        assert len(arrival) == 3
        # The shell (first arrival) precedes the deferred OOB chunks by a margin
        # comparable to the awaitable delay — a buffer-then-flush impl would
        # deliver everything at roughly the same instant.
        assert arrival[-1] - arrival[0] > 0.02


class TestSuspenseOffLoopContextPropagation:
    """get_request() and the live CSP nonce survive the off-loop render (#181/#191)."""

    @pytest.mark.asyncio
    async def test_get_request_resolves_on_worker_for_shell_and_block(self) -> None:
        """A template global calling get_request() works in both shell and block.

        The render runs on a worker thread, so this only passes because
        ``_render_off_loop`` copies the loop's contextvars onto the worker.
        """
        from chirp.context import request_var

        env = Environment(loader=DictLoader({"req.html": _REQ_GLOBAL_TEMPLATE}))
        _register_deferred_test(env)

        def who() -> str:
            from chirp.context import get_request

            return str(get_request())

        env.add_global("who", who)

        async def load() -> str:
            return "done"

        suspense = Suspense("req.html", data=load())

        sentinel = "req-OFFLOOP-123"
        token = request_var.set(sentinel)  # type: ignore[arg-type]
        try:
            chunks = await _collect_chunks(env, suspense, is_htmx=True)
        finally:
            request_var.reset(token)

        # Shell render (worker) saw the request.
        assert f"shell:{sentinel}" in chunks[0]
        # Deferred block render (worker) also saw the request.
        oob = "".join(chunks[1:])
        assert f"block:{sentinel}:done" in oob

    @pytest.mark.asyncio
    async def test_live_nonce_appears_on_streamed_script_off_loop(self) -> None:
        """A nonce set before the drain is stamped onto the streamed <script>.

        Exercises the same #181 contract as TestSuspenseStreamCarriesLiveNonce
        but is retained here as the #193 acceptance check: the nonce is captured
        by render_suspense and used to format the OOB <script> emitted after the
        block render returns from the worker thread.
        """
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce

        env = _env()

        async def load_stats() -> list[str]:
            return ["alice"]

        async def load_feed() -> list[str]:
            return ["post"]

        suspense = Suspense("dashboard.html", title="T", stats=load_stats(), feed=load_feed())

        live_nonce = "OFFLOOPNONCE"
        token = _set_csp_nonce(live_nonce)
        try:
            chunks = [chunk async for chunk in render_suspense(env, suspense, is_htmx=False)]
        finally:
            _reset_csp_nonce(token)

        body = "".join(chunks)
        assert f'<script nonce="{live_nonce}">' in body
        assert "<script>" not in body  # no un-nonced inline script slipped through

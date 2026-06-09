"""Tests for Alpine.js support — config, injection, dedup, and macros."""

import re
from datetime import date

from kida import Environment, PackageLoader
from kida.template import Markup

from chirp import App
from chirp.config import AppConfig
from chirp.server.alpine import PLUGIN_NAMES, alpine_json_config, alpine_snippet
from chirp.templating.filters import BUILTIN_FILTERS
from chirp.templating.returns import Template
from chirp.testing import TestClient


def _make_env() -> Environment:
    """Create a kida env that can load chirp macros."""
    env = Environment(
        loader=PackageLoader("chirp.templating", "macros"),
        autoescape=True,
    )
    env.update_filters(BUILTIN_FILTERS)
    return env


# ---------------------------------------------------------------------------
# Unit tests — alpine_snippet
# ---------------------------------------------------------------------------


class TestAlpineSnippet:
    def test_default_builds_script_tag(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert 'src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8/dist/cdn.min.js"' in s
        assert 'data-chirp="alpine"' in s
        assert "defer" in s

    def test_includes_focus_plugin(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert "@alpinejs/focus" in s
        assert 'data-chirp="alpine-focus"' in s

    def test_includes_mask_plugin(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert "@alpinejs/mask" in s
        assert 'data-chirp="alpine-mask"' in s

    def test_includes_intersect_plugin(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert "@alpinejs/intersect" in s
        assert 'data-chirp="alpine-intersect"' in s

    def test_includes_safe_data_helper(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert "Alpine.safeData" in s
        assert "_chirpAlpineData" in s

    def test_includes_store_init(self) -> None:
        s = alpine_snippet("3.15.8", csp=False)
        assert 'Alpine.store("modals"' in s
        assert 'Alpine.store("trays"' in s

    def test_csp_uses_csp_build(self) -> None:
        s = alpine_snippet("3.15.8", csp=True)
        assert "@alpinejs/csp@3.15.8/dist/cdn.min.js" in s

    def test_csp_excludes_standard_alpine(self) -> None:
        """CSP build must not include the standard alpinejs core script."""
        s = alpine_snippet("3.15.8", csp=True)
        assert 'src="https://cdn.jsdelivr.net/npm/alpinejs@' not in s

    def test_csp_includes_plugins_and_helper(self) -> None:
        """CSP build still ships plugins and the safeData helper."""
        s = alpine_snippet("3.15.8", csp=True)
        assert "@alpinejs/focus" in s
        assert "@alpinejs/mask" in s
        assert "@alpinejs/intersect" in s
        assert "Alpine.safeData" in s

    def test_safe_data_helper_is_first(self) -> None:
        """safeData helper must appear before Alpine core so it queues early calls."""
        s = alpine_snippet("3.15.8", csp=False)
        helper_pos = s.index("_chirpAlpineData")
        core_pos = s.index('data-chirp="alpine"')
        assert helper_pos < core_pos

    def test_core_url_has_explicit_cdn_path(self) -> None:
        """Bare package paths (alpinejs@version without /dist/cdn.min.js) resolve to
        CommonJS on jsDelivr, which throws ReferenceError in browsers.
        Every script src must use an explicit /dist/cdn.min.js path."""
        s = alpine_snippet("3.15.8", csp=False)
        assert "alpinejs@3.15.8/dist/cdn.min.js" in s

    def test_csp_url_has_explicit_cdn_path(self) -> None:
        """CSP build must also use explicit /dist/cdn.min.js — same CJS footgun."""
        s = alpine_snippet("3.15.8", csp=True)
        assert "@alpinejs/csp@3.15.8/dist/cdn.min.js" in s

    def test_no_bare_package_urls(self) -> None:
        """Guard: no script src should end with a bare @version (no subpath).

        jsDelivr resolves bare npm paths to package.json "main", which for
        Alpine.js is dist/module.cjs.js — a CommonJS module that throws
        ReferenceError: module is not defined in the browser.
        """
        s = alpine_snippet("3.15.8", csp=False)
        bare_urls = re.findall(r'src="[^"]+@[0-9.]+"', s)
        assert not bare_urls, f"Bare package script URLs (no /dist/...): {bare_urls}"
        s_csp = alpine_snippet("3.15.8", csp=True)
        bare_csp = re.findall(r'src="[^"]+@[0-9.]+"', s_csp)
        assert not bare_csp, f"Bare package script URLs in CSP build: {bare_csp}"

    def test_bare_url_pattern_detects_known_bad_url(self) -> None:
        """Guard: regex must match a known-bad bare URL so the test is not vacuous."""
        bad = 'src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"'
        assert re.findall(r'src="[^"]+@[0-9.]+"', bad) == [bad]

    def test_plugin_urls_have_explicit_cdn_path(self) -> None:
        """Each plugin script src must include @alpinejs/{name}@…/dist/cdn.min.js."""
        snippet = alpine_snippet("3.15.8", csp=False)
        for plugin in PLUGIN_NAMES:
            assert re.search(
                rf"@alpinejs/{plugin}@3\.15\.8/dist/cdn\.min\.js",
                snippet,
            ), f"Missing explicit /dist/cdn.min.js for plugin: {plugin}"

    def test_plugin_versions_follow_requested_alpine_version(self) -> None:
        """Plugin URLs should stay aligned with the configured Alpine version."""
        snippet = alpine_snippet("3.16.1", csp=False)
        for plugin in PLUGIN_NAMES:
            assert f"@alpinejs/{plugin}@3.16.1/dist/cdn.min.js" in snippet


# ---------------------------------------------------------------------------
# alpine_json_config template global
# ---------------------------------------------------------------------------


class TestAlpineJsonConfig:
    def test_basic_output(self) -> None:
        out = alpine_json_config("my-id", {"key": "value"})
        assert str(out) == ('<script id="my-id" type="application/json">{"key": "value"}</script>')

    def test_id_escaping(self) -> None:
        out = alpine_json_config('a"b', {})
        assert 'id="a&quot;b"' in str(out)

    def test_escapes_ampersand_and_brackets_in_id(self) -> None:
        out = alpine_json_config("x&y<z>", {})
        assert 'id="x&amp;y&lt;z&gt;"' in str(out)

    def test_script_close_sequence_in_data(self) -> None:
        out = alpine_json_config("cfg", {"html": "</script><script>evil"})
        s = str(out)
        assert "</script><script>" not in s
        assert "<\\/script>" in s or "<\\/scr" in s

    def test_non_json_serializable_uses_default_str(self) -> None:
        out = alpine_json_config("d", {"when": date(2026, 4, 11)})
        assert "2026-04-11" in str(out)

    def test_returns_markup(self) -> None:
        out = alpine_json_config("x", {})
        assert isinstance(out, Markup)

    def test_none_serializes_to_null(self) -> None:
        out = alpine_json_config("n", None)
        assert str(out) == '<script id="n" type="application/json">null</script>'


class TestAlpineJsonConfigTemplateRender:
    """``alpine_json_config`` is available to Kida when ``alpine=True``."""

    def test_render_inline_template_emits_script_tag(self) -> None:
        app = App(config=AppConfig(alpine=True, template_dir="nonexistent"))

        @app.route("/")
        def index():
            return "ok"

        html = app.render(
            Template.inline(
                '{{ alpine_json_config("app-cfg", cfg) }}',
                cfg={"rows": 1},
            )
        )
        assert '<script id="app-cfg" type="application/json">' in html
        assert '"rows": 1' in html


# ---------------------------------------------------------------------------
# Integration tests — injection via App._freeze()
# ---------------------------------------------------------------------------


class TestAlpineInjection:
    async def test_injected_when_alpine_enabled(self) -> None:
        """alpine=True injects the Alpine script in full-page HTML."""
        app = App(config=AppConfig(alpine=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="alpine"' in response.text
            assert "cdn.jsdelivr.net/npm/alpinejs" in response.text
            assert "@alpinejs/focus" in response.text
            assert "Alpine.safeData" in response.text

    async def test_not_injected_when_alpine_disabled(self) -> None:
        """alpine=False (default) does not inject."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "alpinejs" not in response.text

    async def test_not_injected_on_fragment(self) -> None:
        """htmx fragment requests do not get Alpine."""
        app = App(config=AppConfig(alpine=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "alpinejs" not in response.text

    async def test_not_injected_on_json(self) -> None:
        """JSON responses are untouched."""
        app = App(config=AppConfig(alpine=True))

        @app.route("/api")
        def api():
            return {"key": "value"}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert "alpinejs" not in response.text

    async def test_uses_config_version(self) -> None:
        """alpine_version from config is used in the script URL."""
        app = App(config=AppConfig(alpine=True, alpine_version="3.14.0"))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "alpinejs@3.14.0" in response.text

    async def test_alpine_json_config_registered_when_alpine_enabled(self) -> None:
        app = App(config=AppConfig(alpine=True))

        @app.route("/")
        def index():
            return "<html><body></body></html>"

        async with TestClient(app):
            assert app._kida_env is not None
            assert "alpine_json_config" in app._kida_env.globals

    async def test_alpine_json_config_not_registered_when_alpine_disabled(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "<html><body></body></html>"

        async with TestClient(app):
            assert app._kida_env is not None
            assert "alpine_json_config" not in app._kida_env.globals


# ---------------------------------------------------------------------------
# AlpineInject deduplication tests
# ---------------------------------------------------------------------------


class TestAlpineInjectDedup:
    async def test_skips_injection_when_alpine_already_present(self) -> None:
        """AlpineInject does not double-inject if page already has Alpine."""
        app = App(config=AppConfig(alpine=True))

        @app.route("/")
        def index():
            return (
                "<html><body>"
                '<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js" '
                'data-chirp="alpine"></script>'
                "</body></html>"
            )

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            body = response.text
            count = body.count('data-chirp="alpine"')
            assert count == 1, f"Expected 1 Alpine marker, found {count}"

    async def test_injects_when_alpine_not_present(self) -> None:
        """AlpineInject adds Alpine to a page that lacks it."""
        app = App(config=AppConfig(alpine=True))

        @app.route("/")
        def index():
            return "<html><body><h1>No Alpine here</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="alpine"' in response.text


# ---------------------------------------------------------------------------
# AlpineInject CSP-nonce tests (#195) — the inline safeData bootstrap must carry
# the live per-request nonce so a standard alpine=True app runs under a strict
# nonce-only CSP without alpine_csp=True.
# ---------------------------------------------------------------------------


class TestAlpineInjectNonce:
    """The inline safeData <script> carries the live request nonce."""

    @staticmethod
    def _factory():
        """Mirror the compiler's per-request snippet factory."""
        return lambda nonce: alpine_snippet("3.15.8", False, nonce=nonce)

    @staticmethod
    def _safe_data_script(text: str) -> str:
        """Return the inline safeData <script>...</script> from injected HTML.

        The plugin/core tags are external ``src=`` scripts; the only inline
        script is the safeData bootstrap, identified by ``_chirpAlpineData``.
        """
        marker = "_chirpAlpineData"
        assert marker in text, "safeData bootstrap not injected"
        start = text.rfind("<script", 0, text.index(marker))
        end = text.index("</script>", text.index(marker)) + len("</script>")
        return text[start:end]

    async def test_buffered_full_page_carries_live_nonce(self) -> None:
        from chirp.http.response import Response
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce
        from chirp.middleware.inject import AlpineInject

        class FakeRequest:
            is_htmx = False

        mw = AlpineInject(self._factory(), full_page_only=True)

        async def next_ok(_req: object) -> Response:
            return Response(
                body="<html><body><h1>Hi</h1></body></html>",
                content_type="text/html; charset=utf-8",
            )

        token = _set_csp_nonce("LIVE-NONCE-123")
        try:
            resp = await mw(FakeRequest(), next_ok)
        finally:
            _reset_csp_nonce(token)

        assert isinstance(resp, Response)
        text = resp.body if isinstance(resp.body, str) else resp.body.decode()
        inline = self._safe_data_script(text)
        assert 'nonce="LIVE-NONCE-123"' in inline
        # External plugin/core tags must NOT be nonced (they need no nonce).
        assert 'src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8/dist/cdn.min.js"' in text
        assert "@alpinejs/focus" in text

    async def test_streaming_suspense_shell_carries_live_nonce(self) -> None:
        from chirp.http.response import StreamingResponse
        from chirp.middleware.csp_nonce import _reset_csp_nonce, _set_csp_nonce
        from chirp.middleware.inject import AlpineInject

        class FakeRequest:
            is_htmx = False

        mw = AlpineInject(self._factory(), full_page_only=True)

        async def next_ok(_req: object) -> StreamingResponse:
            def chunks():
                yield "<!DOCTYPE html><html><head></head><body>ok"
                yield "</body></html>"

            return StreamingResponse(chunks=chunks())

        token = _set_csp_nonce("STREAM-NONCE-456")
        try:
            resp = await mw(FakeRequest(), next_ok)
            assert isinstance(resp, StreamingResponse)
            parts = [chunk async for chunk in resp.chunks]
        finally:
            _reset_csp_nonce(token)

        text = "".join(parts)
        inline = self._safe_data_script(text)
        assert 'nonce="STREAM-NONCE-456"' in inline
        assert "cdn.jsdelivr.net/npm/alpinejs" in text

    async def test_no_nonce_when_nonces_disabled(self) -> None:
        """No live nonce in scope -> bootstrap injected without a nonce attr."""
        from chirp.http.response import Response
        from chirp.middleware.inject import AlpineInject

        class FakeRequest:
            is_htmx = False

        mw = AlpineInject(self._factory(), full_page_only=True)

        async def next_ok(_req: object) -> Response:
            return Response(
                body="<html><body>x</body></html>",
                content_type="text/html; charset=utf-8",
            )

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, Response)
        text = resp.body if isinstance(resp.body, str) else resp.body.decode()
        inline = self._safe_data_script(text)
        assert "nonce=" not in inline

    async def test_string_snippet_backward_compatible(self) -> None:
        """A plain string snippet (legacy callers) still injects verbatim."""
        from chirp.http.response import Response
        from chirp.middleware.inject import AlpineInject

        class FakeRequest:
            is_htmx = False

        mw = AlpineInject("<!--ALPINE-->", full_page_only=True)

        async def next_ok(_req: object) -> Response:
            return Response(
                body="<html><body>x</body></html>",
                content_type="text/html; charset=utf-8",
            )

        resp = await mw(FakeRequest(), next_ok)
        assert isinstance(resp, Response)
        text = resp.body if isinstance(resp.body, str) else resp.body.decode()
        assert "<!--ALPINE--></body>" in text

    async def test_end_to_end_nonce_under_csp_nonce_middleware(self) -> None:
        """Full app: alpine=True + CSPNonceMiddleware emits a nonced bootstrap
        whose nonce matches the response CSP header — no alpine_csp needed."""
        import re

        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        app = App(config=AppConfig(alpine=True))
        app.add_middleware(CSPNonceMiddleware())

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            csp = response.header("content-security-policy") or ""
            m = re.search(r"'nonce-([^']+)'", csp)
            assert m, f"no nonce in CSP header: {csp!r}"
            nonce = m.group(1)
            inline = TestAlpineInjectNonce._safe_data_script(response.text)
            assert f'nonce="{nonce}"' in inline


class TestAllFrameworkInlineScriptsNonced:
    """#195: every framework inline-script injection (not just Alpine) is built
    through a per-request snippet factory, so it carries the live response nonce
    under CSPNonceMiddleware. This covers safe_target, sse_lifecycle, delegation,
    view_transitions, islands, and Alpine wired through the real compiler."""

    async def test_all_enabled_features_carry_response_nonce(self) -> None:
        import re

        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        app = App(
            config=AppConfig(
                alpine=True,
                safe_target=True,
                sse_lifecycle=True,
                delegation=True,
                view_transitions=True,
                islands=True,
            )
        )
        app.add_middleware(CSPNonceMiddleware())

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            csp = response.header("content-security-policy") or ""
            m = re.search(r"'nonce-([^']+)'", csp)
            assert m, f"no nonce in CSP header: {csp!r}"
            nonce = m.group(1)
            body = response.text

            # Each framework inline script carries the live response nonce.
            for marker in (
                "safe-target",
                "sse-lifecycle",
                "delegation",
                "view-transitions",
                "islands",
            ):
                assert f'data-chirp="{marker}" nonce="{nonce}"' in body, (
                    f"{marker} inline script not nonced with response nonce"
                )

            # Alpine's inline safeData bootstrap is nonced too.
            assert "_chirpAlpineData" in body
            alpine_start = body.rfind("<script", 0, body.index("_chirpAlpineData"))
            alpine_end = body.index("</script>", body.index("_chirpAlpineData"))
            assert f'nonce="{nonce}"' in body[alpine_start:alpine_end]

            # No bare inline <script> slipped through under the nonce CSP. (The
            # external Alpine plugin/core scripts are `<script defer src=...>`,
            # never `<script>`.)
            assert "<script>" not in body


# ---------------------------------------------------------------------------
# Macro tests — dropdown, modal, tabs
# ---------------------------------------------------------------------------


class TestAlpineMacros:
    def test_dropdown_renders_x_data_and_x_show(self) -> None:
        env = _make_env()
        source = """
{% from "chirp/alpine.html" import dropdown %}
{% call dropdown("Menu") %}
  <a href="/a">Link A</a>
{% end %}
"""
        tpl = env.from_string(source)
        html = tpl.render().strip()
        assert "open: false" in html
        assert "x-show" in html
        assert "open" in html
        assert "Menu" in html
        assert "Link A" in html
        assert "chirp-dropdown" in html

    def test_modal_renders_managed_by_default(self) -> None:
        env = _make_env()
        source = """
{% from "chirp/alpine.html" import modal %}
{% call modal("my-modal", title="Confirm") %}
  <p>Are you sure?</p>
{% end %}
"""
        tpl = env.from_string(source)
        html = tpl.render().strip()
        assert "x-data" in html
        assert "open: false" in html
        assert "x-show" in html
        assert "open" in html
        assert 'id="my-modal"' in html
        assert "Confirm" in html
        assert "Are you sure?" in html
        assert 'role="dialog"' in html

    def test_modal_managed_false_omits_x_data(self) -> None:
        env = _make_env()
        source = """
{% from "chirp/alpine.html" import modal %}
{% call modal("my-modal", managed=false) %}
  <p>Content</p>
{% end %}
"""
        tpl = env.from_string(source)
        html = tpl.render().strip()
        assert 'x-show="open"' in html
        assert 'x-data="{ open: false }"' not in html

    def test_tabs_renders_tab_list_and_x_data(self) -> None:
        env = _make_env()
        source = """
{% from "chirp/alpine.html" import tabs %}
{% call tabs(["Overview", "Details"], "Overview") %}
  <div x-show="active === 'Overview'">Overview content</div>
  <div x-show="active === 'Details'">Details content</div>
{% end %}
"""
        tpl = env.from_string(source)
        html = tpl.render().strip()
        assert "active" in html
        assert "Overview" in html
        assert "Details" in html
        assert 'role="tablist"' in html
        assert "chirp-tabs" in html

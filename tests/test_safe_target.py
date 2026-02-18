"""Tests for htmx safe target — auto hx-target="this" injection."""

from chirp.app import App
from chirp.config import AppConfig
from chirp.server.htmx_safe_target import SAFE_TARGET_JS, SAFE_TARGET_SNIPPET
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Unit tests — JS constants
# ---------------------------------------------------------------------------


class TestSafeTargetConstants:
    def test_snippet_wraps_js_in_script_tag(self) -> None:
        assert SAFE_TARGET_SNIPPET.startswith('<script data-chirp="safe-target">')
        assert SAFE_TARGET_SNIPPET.endswith("</script>")

    def test_js_contains_idempotency_guard(self) -> None:
        assert "__chirpSafeTarget" in SAFE_TARGET_JS

    def test_js_uses_htmx_onload(self) -> None:
        assert "htmx.onLoad" in SAFE_TARGET_JS

    def test_js_targets_from_trigger_without_explicit_target(self) -> None:
        """The selector matches hx-trigger*=from: with hx-get/post/etc but :not(hx-target)."""
        assert 'hx-trigger*="from:"' in SAFE_TARGET_JS
        assert ":not([hx-target])" in SAFE_TARGET_JS

    def test_js_sets_hx_target_this(self) -> None:
        assert '"hx-target","this"' in SAFE_TARGET_JS


# ---------------------------------------------------------------------------
# Integration tests — injection via App._freeze()
# ---------------------------------------------------------------------------


class TestSafeTargetInjection:
    async def test_injected_on_full_page_by_default(self) -> None:
        """Safe target snippet appears in full-page HTML responses."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="safe-target"' in response.text

    async def test_not_injected_on_fragment(self) -> None:
        """htmx fragment requests do not get the safe target script."""
        app = App()

        @app.route("/count")
        def count():
            return "<span>42</span>"

        async with TestClient(app) as client:
            response = await client.get("/count", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "safe-target" not in response.text

    async def test_disabled_via_config(self) -> None:
        """AppConfig(safe_target=False) suppresses injection."""
        app = App(config=AppConfig(safe_target=False))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "safe-target" not in response.text

    async def test_injected_before_closing_body(self) -> None:
        """The snippet is placed before </body>."""
        app = App()

        @app.route("/")
        def index():
            return "<html><body><p>content</p></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            text = response.text
            snippet_pos = text.find('data-chirp="safe-target"')
            body_close_pos = text.find("</body>")
            assert snippet_pos < body_close_pos

    async def test_coexists_with_debug_overlay(self) -> None:
        """Both safe target and debug overlay are injected when debug=True."""
        app = App(config=AppConfig(debug=True))

        @app.route("/")
        def index():
            return "<html><body><p>content</p></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert 'data-chirp="safe-target"' in response.text
            assert "chirp-debug" in response.text

    async def test_skips_plain_string_without_body_tag(self) -> None:
        """A plain string return (no </body>) is left untouched."""
        app = App()

        @app.route("/")
        def index():
            return "hello world"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.text == "hello world"

    async def test_does_not_touch_json(self) -> None:
        """JSON responses are untouched even with safe_target=True."""
        app = App()

        @app.route("/api")
        def api():
            return {"count": 42}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert "safe-target" not in response.text

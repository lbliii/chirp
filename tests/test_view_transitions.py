"""Tests for View Transitions — auto-inject meta tag, CSS, and htmx config."""

from chirp.app import App
from chirp.config import AppConfig
from chirp.server.view_transitions import (
    VIEW_TRANSITIONS_CSS,
    VIEW_TRANSITIONS_HEAD_SNIPPET,
    VIEW_TRANSITIONS_JS,
    VIEW_TRANSITIONS_SCRIPT_SNIPPET,
)
from chirp.testing import TestClient


# ---------------------------------------------------------------------------
# Unit tests — snippet constants
# ---------------------------------------------------------------------------


class TestViewTransitionsConstants:
    def test_head_snippet_contains_meta_tag(self) -> None:
        assert '<meta name="view-transition" content="same-origin">' in (
            VIEW_TRANSITIONS_HEAD_SNIPPET
        )

    def test_head_snippet_contains_style_tag(self) -> None:
        assert '<style data-chirp="view-transitions">' in VIEW_TRANSITIONS_HEAD_SNIPPET
        assert "</style>" in VIEW_TRANSITIONS_HEAD_SNIPPET

    def test_css_contains_view_transition_at_rule(self) -> None:
        assert "@view-transition { navigation: auto; }" in VIEW_TRANSITIONS_CSS

    def test_css_uses_namespaced_keyframes(self) -> None:
        assert "chirp-vt-out" in VIEW_TRANSITIONS_CSS
        assert "chirp-vt-in" in VIEW_TRANSITIONS_CSS

    def test_css_targets_root_transition(self) -> None:
        assert "::view-transition-old(root)" in VIEW_TRANSITIONS_CSS
        assert "::view-transition-new(root)" in VIEW_TRANSITIONS_CSS

    def test_script_snippet_wraps_js_in_script_tag(self) -> None:
        assert VIEW_TRANSITIONS_SCRIPT_SNIPPET.startswith(
            '<script data-chirp="view-transitions">'
        )
        assert VIEW_TRANSITIONS_SCRIPT_SNIPPET.endswith("</script>")

    def test_js_contains_idempotent_guard(self) -> None:
        assert "__chirpViewTransitions" in VIEW_TRANSITIONS_JS

    def test_js_enables_global_view_transitions(self) -> None:
        assert "globalViewTransitions=true" in VIEW_TRANSITIONS_JS

    def test_js_handles_deferred_htmx(self) -> None:
        """Listener for htmx:load handles the case where htmx loads after the script."""
        assert "htmx:load" in VIEW_TRANSITIONS_JS


# ---------------------------------------------------------------------------
# Integration tests — injection via App._freeze()
# ---------------------------------------------------------------------------

FULL_PAGE = '<html><head><title>T</title></head><body><h1>Hi</h1></body></html>'


class TestViewTransitionsInjection:
    async def test_disabled_by_default(self) -> None:
        """Default config does not inject view transition snippets."""
        app = App()

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "view-transition" not in response.text
            assert "globalViewTransitions" not in response.text

    async def test_injects_meta_tag(self) -> None:
        """view_transitions=True injects the meta tag."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            assert 'name="view-transition"' in response.text

    async def test_injects_css(self) -> None:
        """view_transitions=True injects the default crossfade CSS."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            assert "chirp-vt-out" in response.text
            assert "chirp-vt-in" in response.text

    async def test_injects_script(self) -> None:
        """view_transitions=True injects the htmx config script."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            assert "globalViewTransitions" in response.text

    async def test_meta_and_css_in_head(self) -> None:
        """Meta tag and CSS are injected before </head>."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            text = response.text
            meta_pos = text.find('name="view-transition"')
            head_close_pos = text.find("</head>")
            assert meta_pos < head_close_pos

    async def test_script_before_body_close(self) -> None:
        """The htmx config script is injected before </body>."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            text = response.text
            script_pos = text.find("globalViewTransitions")
            body_close_pos = text.find("</body>")
            assert script_pos < body_close_pos

    async def test_skips_fragments(self) -> None:
        """Fragment (htmx) requests do not get view transition snippets."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/count")
        def count():
            return "<span>42</span>"

        async with TestClient(app) as client:
            response = await client.get("/count", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "view-transition" not in response.text

    async def test_does_not_touch_json(self) -> None:
        """JSON responses are untouched even with view_transitions=True."""
        app = App(config=AppConfig(view_transitions=True))

        @app.route("/api")
        def api():
            return {"count": 42}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert "view-transition" not in response.text

    async def test_coexists_with_other_snippets(self) -> None:
        """View transitions, SSE lifecycle, and safe target all coexist."""
        app = App(config=AppConfig(
            view_transitions=True,
            sse_lifecycle=True,
            safe_target=True,
        ))

        @app.route("/")
        def index():
            return FULL_PAGE

        async with TestClient(app) as client:
            response = await client.get("/")
            assert 'data-chirp="view-transitions"' in response.text
            assert 'data-chirp="sse-lifecycle"' in response.text
            assert 'data-chirp="safe-target"' in response.text

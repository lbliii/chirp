"""Tests for Alpine.js support — config, injection, dedup, and macros."""

from kida import Environment, PackageLoader

from chirp import App
from chirp.config import AppConfig
from chirp.server.alpine import alpine_snippet
from chirp.templating.filters import BUILTIN_FILTERS
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

    def test_safe_data_helper_is_first(self) -> None:
        """safeData helper must appear before Alpine core so it queues early calls."""
        s = alpine_snippet("3.15.8", csp=False)
        helper_pos = s.index("_chirpAlpineData")
        core_pos = s.index('data-chirp="alpine"')
        assert helper_pos < core_pos


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
                '<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3" '
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

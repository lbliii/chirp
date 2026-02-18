"""Tests for islands runtime and template helpers."""

from kida import Environment

from chirp.app import App
from chirp.config import AppConfig
from chirp.server.islands import islands_snippet
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS
from chirp.testing import TestClient


def _make_env() -> Environment:
    env = Environment(autoescape=True)
    env.update_filters(BUILTIN_FILTERS)
    for name, value in BUILTIN_GLOBALS.items():
        env.add_global(name, value)
    return env


class TestIslandsSnippet:
    def test_runtime_has_lifecycle_events(self) -> None:
        s = islands_snippet("1")
        assert 'data-chirp="islands"' in s
        assert "chirp:island:mount" in s
        assert "chirp:island:unmount" in s
        assert "chirp:island:remount" in s


class TestIslandsInjection:
    async def test_injected_when_enabled(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="islands"' in response.text

    async def test_not_injected_on_fragment_request(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert 'data-chirp="islands"' not in response.text

    async def test_not_injected_on_json_response(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/api")
        def api():
            return {"ok": True}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert 'data-chirp="islands"' not in response.text


class TestIslandHelpers:
    def test_island_props_filter_escapes_json(self) -> None:
        env = _make_env()
        tpl = env.from_string('{{ payload | island_props }}')
        rendered = tpl.render({"payload": {"x": "<tag>", "items": [1, 2]}})
        assert "&quot;" in rendered
        assert "<tag>" not in rendered

    def test_island_attrs_global_renders_mount_attrs(self) -> None:
        env = _make_env()
        tpl = env.from_string(
            '<div{{ island_attrs("editor", props=payload, mount_id="editor-root", src="/static/editor.js") }}></div>'
        )
        rendered = tpl.render({"payload": {"doc_id": 42}})
        assert 'data-island="editor"' in rendered
        assert 'id="editor-root"' in rendered
        assert 'data-island-src="/static/editor.js"' in rendered
        assert "data-island-props=" in rendered

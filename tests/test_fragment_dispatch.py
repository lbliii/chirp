"""Tests for the ``/_frag{path}?_b={block}`` block-fetch dispatcher."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.realtime.events import EventStream
from chirp.templating.returns import Fragment, Template
from chirp.testing import TestClient


@pytest.fixture
def app_with_blocks(tmp_path: Path) -> App:
    tmpl_dir = tmp_path / "templates"
    tmpl_dir.mkdir()
    (tmpl_dir / "page.html").write_text(
        "<!doctype html><html><body>\n"
        "{% block header %}<h1>Hello, {{ name }}</h1>{% end %}\n"
        "{% block main %}<p>body for {{ name }}</p>{% end %}\n"
        "{% block footer %}<footer>bye {{ name }}</footer>{% end %}\n"
        "</body></html>\n"
    )
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/hello/{name}")
    def hello(name: str):
        return Template("page.html", name=name)

    @app.route("/plain/{name}")
    def plain(name: str):
        return Fragment("page.html", "header", name=name)

    @app.route("/events", referenced=True)
    def events():
        async def gen():
            yield Fragment("page.html", "main", name="streamed")

        return EventStream(gen())

    return app


class TestFragmentDispatch:
    async def test_returns_named_block_only(self, app_with_blocks: App) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/hello/alice?_b=main")
            assert response.status == 200
            assert "body for alice" in response.text
            assert "<h1>" not in response.text
            assert "<footer>" not in response.text

    async def test_different_block_from_same_page(self, app_with_blocks: App) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/hello/bob?_b=footer")
            assert response.status == 200
            assert "bye bob" in response.text
            assert "Hello, bob" not in response.text

    async def test_missing_block_param_returns_400(self, app_with_blocks: App) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/hello/alice")
            assert response.status == 400

    async def test_unknown_underlying_path_returns_404(self, app_with_blocks: App) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/nope/zzz?_b=main")
            assert response.status == 404

    async def test_handler_returning_fragment_passes_through(
        self, app_with_blocks: App
    ) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/plain/carol?_b=header")
            assert response.status == 200
            # Handler hard-codes block "header" and ignores _b — that's fine
            assert "Hello, carol" in response.text

    async def test_referenced_routes_are_not_block_addressable(
        self, app_with_blocks: App
    ) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/events?_b=main")
            assert response.status == 404

    async def test_cannot_recurse_into_dispatcher(self, app_with_blocks: App) -> None:
        async with TestClient(app_with_blocks) as client:
            response = await client.get("/_frag/_frag/hello/alice?_b=main")
            assert response.status == 400


class TestReservedPrefixCollision:
    def test_user_route_under_frag_prefix_raises(self, tmp_path: Path) -> None:
        from chirp.errors import ConfigurationError

        app = App(config=AppConfig(template_dir=str(tmp_path), debug=False))

        @app.route("/_frag/custom")
        def custom():
            return "nope"

        with pytest.raises(ConfigurationError) as exc_info:
            app.freeze()
        assert "/_frag/custom" in str(exc_info.value)
        assert "reserved prefix" in str(exc_info.value)

    def test_exact_frag_prefix_raises(self, tmp_path: Path) -> None:
        from chirp.errors import ConfigurationError

        app = App(config=AppConfig(template_dir=str(tmp_path), debug=False))

        @app.route("/_frag")
        def bare():
            return "nope"

        with pytest.raises(ConfigurationError):
            app.freeze()

    def test_unrelated_underscore_routes_are_fine(self, tmp_path: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmp_path), debug=False))

        @app.route("/_foo")
        def foo():
            return "ok"

        @app.route("/_frag_like_but_not")
        def fraglike():
            return "ok"

        app.freeze()


class TestFragmentUrlBuilder:
    def test_basic_path(self) -> None:
        from chirp.server.fragment_dispatch import fragment_url

        assert fragment_url("/docs/intro", "recent_updates") == (
            "/_frag/docs/intro?_b=recent_updates"
        )

    def test_missing_leading_slash_is_normalized(self) -> None:
        from chirp.server.fragment_dispatch import fragment_url

        assert fragment_url("docs/intro", "foo") == "/_frag/docs/intro?_b=foo"

    def test_trailing_slash_preserved(self) -> None:
        from chirp.server.fragment_dispatch import fragment_url

        assert fragment_url("/docs/intro/", "foo") == "/_frag/docs/intro/?_b=foo"

    def test_registry_delegates_to_fragment_url(self) -> None:
        from chirp.templating.fragment_target_registry import FragmentTargetRegistry

        assert FragmentTargetRegistry.external_url("/foo", "bar") == "/_frag/foo?_b=bar"

    def test_fragment_url_is_a_template_global(self, tmp_path: Path) -> None:
        tmpl_dir = tmp_path / "tmpl"
        tmpl_dir.mkdir()
        (tmpl_dir / "p.html").write_text(
            "<a href=\"{{ fragment_url('/docs/intro', 'recent_updates') }}\">x</a>"
        )
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/view")
        def view():
            return Template("p.html")

        app.freeze()
        tmpl = app._runtime_state.kida_env.get_template("p.html")
        rendered = tmpl.render({})
        assert rendered == '<a href="/_frag/docs/intro?_b=recent_updates">x</a>'


class TestFragmentRouteRegistration:
    def test_dispatcher_registered_on_freeze(self, tmp_path: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmp_path), debug=False))
        app.freeze()
        paths = {r.path for r in app._runtime_state.router.routes}
        assert "/_frag/{path:path}" in paths

    def test_dispatcher_is_referenced(self, tmp_path: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmp_path), debug=False))
        app.freeze()
        dispatcher = next(
            r
            for r in app._runtime_state.router.routes
            if r.path == "/_frag/{path:path}"
        )
        assert dispatcher.referenced is True
        assert dispatcher.name == "chirp_fragment_dispatch"

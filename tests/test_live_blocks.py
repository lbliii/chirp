"""Tests for the ``@app.live_block`` decorator and its contract checks."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.live_blocks import LiveBlockSpec
from chirp.templating.returns import Fragment, Template


@pytest.fixture
def tmpl_dir(tmp_path: Path) -> Path:
    d = tmp_path / "templates"
    d.mkdir()
    (d / "page.html").write_text(
        "<!doctype html><html><body>\n"
        "{% block header %}<h1>{{ slug }}</h1>{% end %}\n"
        "{% block body %}<p>body {{ slug }}</p>{% end %}\n"
        "{% block recent_updates %}<div>updates</div>{% end %}\n"
        "</body></html>\n"
    )
    return d


class TestLiveBlockDecorator:
    def test_decorator_registers_spec(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/docs/{slug}")
        def show(slug: str):
            return Template("page.html", slug=slug)

        @app.live_block("/docs/{slug}", "recent_updates")
        async def recent(slug: str):
            return Fragment("page.html", "recent_updates", slug=slug)

        spec = app._mutable_state.live_blocks[("/docs/{slug}", "recent_updates")]
        assert isinstance(spec, LiveBlockSpec)
        assert spec.route == "/docs/{slug}"
        assert spec.block == "recent_updates"
        assert spec.handler is recent
        assert spec.trigger == "load"
        assert spec.swap == "innerHTML"
        assert spec.skeleton is None
        assert spec.cache_seconds is None

    def test_decorator_forwards_options(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.live_block(
            "/x",
            "header",
            trigger="load delay:100ms",
            swap="outerHTML",
            skeleton="<div class='skel'></div>",
            cache_seconds=60,
        )
        def h():
            return Fragment("page.html", "header")

        spec = app._mutable_state.live_blocks[("/x", "header")]
        assert spec.trigger == "load delay:100ms"
        assert spec.swap == "outerHTML"
        assert spec.skeleton == "<div class='skel'></div>"
        assert spec.cache_seconds == 60

    def test_returned_handler_is_the_original(self, tmpl_dir: Path) -> None:
        """Decorator must return the original function unchanged."""
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        def handler():
            return Fragment("page.html", "header")

        wrapped = app.live_block("/x", "header")(handler)
        assert wrapped is handler

    def test_decorator_raises_after_freeze(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))
        app.freeze()
        with pytest.raises(RuntimeError):

            @app.live_block("/x", "header")
            def h():
                return Fragment("page.html", "header")


class TestLiveBlockChecks:
    def test_unreachable_route_flagged(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.live_block("/nope", "header")
        def h():
            return Fragment("page.html", "header")

        result = check_hypermedia_surface(app)
        cats = {i.category for i in result.issues}
        assert "live_block_unreachable_route" in cats

    def test_unknown_block_flagged(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/x")
        def show():
            return Template("page.html", slug="x")

        # route_templates isn't populated for imperative routes, but the
        # checker falls back to scanning the handler source for a template
        # reference — so this still validates.
        @app.live_block("/x", "nonexistent")
        def bad():
            return Fragment("page.html", "nonexistent")

        result = check_hypermedia_surface(app)
        cats = {i.category for i in result.issues}
        assert "live_block_unknown" in cats

    def test_valid_declaration_passes(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/x")
        def show():
            return Template("page.html", slug="x")

        @app.live_block("/x", "recent_updates")
        def live():
            return Fragment("page.html", "recent_updates")

        result = check_hypermedia_surface(app)
        for issue in result.issues:
            assert issue.category not in {
                "live_block_unknown",
                "live_block_unreachable_route",
            }

    def test_no_live_blocks_is_noop(self, tmpl_dir: Path) -> None:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/x")
        def show():
            return Template("page.html", slug="x")

        result = check_hypermedia_surface(app)
        cats = {i.category for i in result.issues}
        assert "live_block_unknown" not in cats
        assert "live_block_unreachable_route" not in cats

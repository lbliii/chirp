"""Tests for ``chirp freeze`` live-block placeholder rewriting."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.freeze import freeze
from chirp.templating.returns import Fragment, Template


@pytest.fixture
def tmpl_dir(tmp_path: Path) -> Path:
    d = tmp_path / "templates"
    d.mkdir()
    (d / "page.html").write_text(
        "<!doctype html><html><body>\n"
        "<h1>{{ title }}</h1>\n"
        "{% block static_hero %}<section>STATIC-HERO for {{ title }}</section>{% end %}\n"
        "{% block recent_updates %}"
        "<ul class='updates'>"
        "<li>u1 for {{ title }}</li>"
        "<li>u2 for {{ title }}</li>"
        "</ul>"
        "{% end %}\n"
        "</body></html>\n"
    )
    return d


async def test_live_block_rewritten_to_placeholder(tmpl_dir: Path, tmp_path: Path) -> None:
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/hello")
    def show():
        return Template("page.html", title="World")

    @app.live_block("/hello", "recent_updates")
    def live():
        return Fragment("page.html", "recent_updates", title="World")

    output = tmp_path / "dist"
    result = await freeze(app, output)
    assert result.errors == []

    html = (output / "hello" / "index.html").read_text()

    assert "<ul class='updates'>" not in html
    assert "u1 for World" not in html

    assert 'hx-get="/_frag/hello?_b=recent_updates"' in html
    assert 'hx-trigger="load"' in html
    assert 'hx-swap="innerHTML"' in html
    assert 'data-chirp-live="recent_updates"' in html

    assert "STATIC-HERO for World" in html


async def test_no_live_blocks_produces_identical_output(tmpl_dir: Path, tmp_path: Path) -> None:
    """Invariant 1 — pure-static freeze is byte-identical with/without the feature."""

    def build_app() -> App:
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/hello")
        def show():
            return Template("page.html", title="World")

        return app

    out_a = tmp_path / "dist_a"
    await freeze(build_app(), out_a)

    out_b = tmp_path / "dist_b"
    await freeze(build_app(), out_b)

    html_a = (out_a / "hello" / "index.html").read_bytes()
    html_b = (out_b / "hello" / "index.html").read_bytes()
    assert html_a == html_b

    assert b"/_frag/" not in html_a
    assert b"data-chirp-live" not in html_a


async def test_skeleton_rendered_in_placeholder(tmpl_dir: Path, tmp_path: Path) -> None:
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/hello")
    def show():
        return Template("page.html", title="World")

    @app.live_block(
        "/hello",
        "recent_updates",
        skeleton="<div class='skel'>Loading…</div>",
        trigger="load delay:100ms",
    )
    def live():
        return Fragment("page.html", "recent_updates", title="World")

    output = tmp_path / "dist"
    await freeze(app, output)
    html = (output / "hello" / "index.html").read_text()

    assert "<div class='skel'>Loading…</div>" in html
    assert 'hx-trigger="load delay:100ms"' in html


async def test_non_live_block_untouched(tmpl_dir: Path, tmp_path: Path) -> None:
    """Only the declared block gets rewritten; siblings stay static."""
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/hello")
    def show():
        return Template("page.html", title="World")

    @app.live_block("/hello", "recent_updates")
    def live():
        return Fragment("page.html", "recent_updates", title="World")

    output = tmp_path / "dist"
    await freeze(app, output)
    html = (output / "hello" / "index.html").read_text()

    assert "<section>STATIC-HERO for World</section>" in html
    assert 'data-chirp-live="static_hero"' not in html


async def test_origin_500_leaves_skeleton_visible(tmpl_dir: Path, tmp_path: Path) -> None:
    """When the origin returns 500 the placeholder stays intact in frozen HTML.

    The graceful-degradation guarantee: frozen pages must be viewable even if
    the origin is unreachable. htmx will fail the swap silently and leave the
    skeleton content on the page.
    """
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/hello")
    def show():
        return Template("page.html", title="World")

    @app.live_block(
        "/hello",
        "recent_updates",
        skeleton="<div class='fallback'>No updates available.</div>",
    )
    def live():
        raise RuntimeError("origin unavailable")

    output = tmp_path / "dist"
    await freeze(app, output)
    html = (output / "hello" / "index.html").read_text()

    assert "<div class='fallback'>No updates available.</div>" in html
    assert 'hx-get="/_frag/hello?_b=recent_updates"' in html


async def test_parametric_route_placeholder_uses_concrete_url(
    tmpl_dir: Path, tmp_path: Path
) -> None:
    app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

    @app.route("/docs/{slug}")
    def show(slug: str):
        return Template("page.html", title=slug)

    @app.freeze_params("/docs/{slug}")
    def params():
        return [{"slug": "intro"}, {"slug": "advanced"}]

    @app.live_block("/docs/{slug}", "recent_updates")
    def live(slug: str):
        return Fragment("page.html", "recent_updates", title=slug)

    output = tmp_path / "dist"
    await freeze(app, output)

    intro_html = (output / "docs" / "intro" / "index.html").read_text()
    assert 'hx-get="/_frag/docs/intro?_b=recent_updates"' in intro_html
    assert "u1 for intro" not in intro_html

    adv_html = (output / "docs" / "advanced" / "index.html").read_text()
    assert 'hx-get="/_frag/docs/advanced?_b=recent_updates"' in adv_html
    assert "u1 for advanced" not in adv_html

"""Tests for static DOM integrity contract rules (#238)."""

from __future__ import annotations

from chirp import App, AppConfig, EventStream, Fragment
from chirp.contracts import Severity, check_hypermedia_surface
from chirp.contracts.rules_static_dom import (
    check_duplicate_static_ids,
    check_oob_fragment_producers,
    infer_fragment_producers,
)
from chirp.contracts.rules_swap import check_swap_safety
from chirp.routing.router import Route, Router


class TestSelectInheritanceGuidance:
    def test_recommends_hx_select_override_not_disinherit(self):
        template_sources = {
            "_layouts/base.html": (
                '<main hx-boost="true" hx-select="#page-content">'
                "{% block content %}{% endblock %}"
                "</main>"
            ),
            "pages/edit.html": (
                '{% extends "../_layouts/base.html" %}'
                "{% block content %}"
                '<form hx-post="/save"><button>Save</button></form>'
                "{% endblock %}"
            ),
        }

        issues = check_swap_safety(template_sources)

        assert len(issues) == 1
        assert issues[0].category == "select_inheritance"
        assert 'hx-select="unset"' in issues[0].message
        assert "hx-disinherit" not in issues[0].message


class TestDuplicateStaticIds:
    def test_warns_on_repeated_static_id(self):
        issues = check_duplicate_static_ids(
            {
                "page.html": (
                    '<div id="panel">one</div><section id="panel">two</section>'
                ),
            }
        )

        assert len(issues) == 1
        assert issues[0].category == "duplicate_id"
        assert issues[0].severity == Severity.WARNING
        assert 'id="panel"' in issues[0].message

    def test_skips_chirpui_templates(self):
        issues = check_duplicate_static_ids(
            {"chirpui/shell.html": '<div id="x"></div><div id="x"></div>'}
        )
        assert issues == []


class TestOobFragmentProducers:
    def test_warns_when_oob_fragment_has_no_producer(self):
        template_sources = {
            "layout.html": (
                "{% fragment ticker_strip_sse %}"
                '<div id="ticker" hx-swap-oob="innerHTML">waiting</div>'
                "{% endfragment %}"
            ),
        }

        def dead_stream():
            async def generate():
                if False:
                    yield Fragment("layout.html", "other_block")

            return EventStream(generate())

        router = Router()
        router.add(Route("/events", dead_stream, methods=frozenset({"GET"})))

        issues = check_oob_fragment_producers(template_sources, router)

        assert len(issues) == 1
        assert issues[0].category == "oob_fragment_orphan"
        assert "ticker_strip_sse" in issues[0].message

    def test_no_warning_when_route_yields_fragment(self):
        template_sources = {
            "layout.html": (
                "{% fragment ticker_strip_sse %}"
                '<div id="ticker" hx-swap-oob="innerHTML">live</div>'
                "{% endfragment %}"
            ),
        }

        def stream():
            async def generate():
                yield Fragment("layout.html", "ticker_strip_sse")

            return EventStream(generate())

        router = Router()
        router.add(Route("/events", stream, methods=frozenset({"GET"})))

        issues = check_oob_fragment_producers(template_sources, router)

        assert issues == []

    def test_infer_fragment_producers_finds_yield_in_nested_generator(self):
        def stream():
            async def generate():
                yield Fragment("layout.html", "ticker_strip_sse")

            return EventStream(generate())

        produced, blocks = infer_fragment_producers(stream)
        assert produced == {("layout.html", "ticker_strip_sse")}
        assert blocks == {"ticker_strip_sse"}


class TestStaticDomIntegration:
    def test_app_check_surfaces_duplicate_id(self, tmp_path):
        tmpl = tmp_path / "templates"
        tmpl.mkdir()
        (tmpl / "page.html").write_text(
            "<!doctype html><html><body>"
            '<div id="dup"></div><span id="dup"></span>'
            "</body></html>"
        )
        app = App(config=AppConfig(template_dir=str(tmpl), debug=False))

        @app.route("/")
        def index():
            from chirp import Template

            return Template("page.html")

        app.freeze()
        result = check_hypermedia_surface(app)
        dup_issues = [i for i in result.issues if i.category == "duplicate_id"]
        assert dup_issues

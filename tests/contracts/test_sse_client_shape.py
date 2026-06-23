"""Tests for SSE client-shape contract checks."""

from chirp.contracts import Severity
from chirp.contracts.rules_sse_client_shape import (
    check_sse_eager_connect,
    check_sse_token_swap_mode,
)


class _Route:
    def __init__(self, path: str, handler):
        self.path = path
        self.handler = handler
        self.methods = frozenset({"GET"})


class _Router:
    def __init__(self, routes):
        self.routes = routes


def test_warns_innerhtml_on_multi_fragment_stream():
    async def stream(request):
        from chirp import EventStream, Fragment

        async def generate():
            async for word in ["a", "b"]:
                yield Fragment("part.html", "token", token=word)

        return EventStream(generate())

    router = _Router([_Route("/stream", stream)])
    template_sources = {
        "index.html": (
            "<!DOCTYPE html><html><body>"
            '<div hx-ext="sse" sse-connect="/stream?prompt=hi" sse-close="close" '
            'hx-disinherit="hx-target hx-swap">'
            '<div sse-swap="message" hx-target="this" hx-swap="innerHTML"></div>'
            "</div></body></html>"
        ),
        "part.html": "{% block token %}<span>{{ token }}</span>{% endblock %}",
    }
    issues = check_sse_token_swap_mode(template_sources, router)
    assert len(issues) == 1
    assert issues[0].category == "sse_token_swap_mode"
    assert issues[0].severity == Severity.WARNING


def test_no_warning_for_beforeend_on_multi_fragment_stream():
    async def stream(request):
        from chirp import EventStream, Fragment

        async def generate():
            async for word in ["a", "b"]:
                yield Fragment("part.html", "token", token=word)

        return EventStream(generate())

    router = _Router([_Route("/stream", stream)])
    template_sources = {
        "panel.html": (
            '<div hx-ext="sse" sse-connect="/stream?prompt=hi">'
            '<div sse-swap="message" hx-target="this" hx-swap="beforeend"></div>'
            "</div>"
        ),
        "part.html": "{% block token %}<span>{{ token }}</span>{% endblock %}",
    }
    issues = check_sse_token_swap_mode(template_sources, router)
    assert issues == []


def test_no_warning_for_single_fragment_sse_scaffold():
    async def stream(request):
        from chirp import EventStream, Fragment

        async def events():
            yield Fragment("index.html", "stream_block", text="hi")

        return EventStream(events())

    router = _Router([_Route("/stream", stream)])
    template_sources = {
        "index.html": (
            "<!DOCTYPE html><html><body>"
            '<div sse-connect="/stream" hx-disinherit="hx-target hx-swap">'
            '<div sse-swap="stream_block" hx-target="this"></div>'
            "</div></body></html>"
        ),
    }
    issues = check_sse_token_swap_mode(template_sources, router)
    assert issues == []


def test_sse_eager_connect_info_on_static_page_connect():
    template_sources = {
        "feed.html": (
            "<!DOCTYPE html><html><body>"
            '<div sse-connect="/events" sse-close="close"></div>'
            "</body></html>"
        ),
    }
    issues = check_sse_eager_connect(template_sources)
    assert len(issues) == 1
    assert issues[0].category == "sse_eager_connect"
    assert issues[0].severity == Severity.INFO


def test_sse_eager_connect_skips_intentional_marker():
    template_sources = {
        "feed.html": (
            "{# sse-eager-connect: intentional #}"
            "<!DOCTYPE html><html><body>"
            '<div sse-connect="/events"></div>'
            "</body></html>"
        ),
    }
    issues = check_sse_eager_connect(template_sources)
    assert issues == []


def test_sse_eager_connect_skips_dynamic_connect():
    template_sources = {
        "panel.html": (
            '<div sse-connect="{{ stream_url }}">'
            '<div sse-swap="message" hx-target="this" hx-swap="beforeend"></div>'
            "</div>"
        ),
    }
    issues = check_sse_eager_connect(template_sources)
    assert issues == []

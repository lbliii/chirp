"""Tests for TemplateStream client-shape contract checks."""

from chirp.contracts import Severity
from chirp.contracts.rules_template_stream import check_template_stream_client_shape


class _Route:
    def __init__(self, path: str, handler):
        self.path = path
        self.handler = handler
        self.methods = frozenset({"POST"})


class _Router:
    def __init__(self, routes):
        self.routes = routes


def test_warns_htmx_swap_into_template_stream_route():
    async def ask(request):
        from chirp import TemplateStream

        return TemplateStream("response.html", prompt="hi", stream=get_stream(""))

    router = _Router([_Route("/ask", ask)])
    template_sources = {
        "index.html": (
            '<form hx-post="/ask" hx-target="#answer" hx-swap="innerHTML">'
            '<input name="prompt"><button>Go</button></form>'
            '<div id="answer"></div>'
        ),
        "response.html": (
            "<!DOCTYPE html><html><body>"
            '<div class="response">{% async for token in stream %}{{ token }}{% end %}</div>'
            "</body></html>"
        ),
    }
    issues = check_template_stream_client_shape(template_sources, router)
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert issues[0].category == "template_stream_client_shape"
    assert "/ask" in issues[0].message
    assert "#answer" in issues[0].details


def test_no_warning_for_plain_form_post_to_template_stream():
    async def ask(request):
        from chirp import TemplateStream

        return TemplateStream("response.html", prompt="hi", stream=get_stream(""))

    router = _Router([_Route("/ask", ask)])
    template_sources = {
        "index.html": '<form action="/ask" method="post"><button>Go</button></form>',
        "response.html": "<!DOCTYPE html><html><body>ok</body></html>",
    }
    issues = check_template_stream_client_shape(template_sources, router)
    assert issues == []


def test_no_warning_for_htmx_swap_to_fragment_route():
    async def ask(request):
        from chirp import Fragment

        return Fragment("part.html", "body")

    router = _Router([_Route("/ask", ask)])
    template_sources = {
        "index.html": (
            '<form hx-post="/ask" hx-target="#answer"><button>Go</button></form>'
            '<div id="answer"></div>'
        ),
        "part.html": "<p>fragment</p>",
    }
    issues = check_template_stream_client_shape(template_sources, router)
    assert issues == []

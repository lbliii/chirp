"""Tests for passthrough and template type negotiation."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.request import Request
from chirp.http.response import Redirect, Response
from chirp.server.negotiation import negotiate
from chirp.templating.composition import PageComposition
from chirp.realtime.events import EventStream
from chirp.templating.returns import (
    Fragment,
    Page,
    Stream,
    Template,
)

class TestNegotiatePassthrough:
    def test_response_passthrough(self) -> None:
        original = Response(body="hello", status=201)
        result = negotiate(original)
        assert result is original

    def test_redirect(self) -> None:
        result = negotiate(Redirect("/login"))
        assert result.status == 302
        assert ("Location", "/login") in result.headers

    def test_redirect_301(self) -> None:
        result = negotiate(Redirect("/new", status=301))
        assert result.status == 301


class TestNegotiateTemplateTypes:
    def test_template_rendering(self, kida_env: Environment) -> None:
        result = negotiate(Template("page.html", title="Home"), kida_env=kida_env)
        assert result.status == 200
        assert "text/html" in result.content_type
        assert "<title>Home</title>" in result.text
        assert "<h1>Home</h1>" in result.text
        assert result.render_intent == "full_page"

    def test_template_with_list(self, kida_env: Environment) -> None:
        result = negotiate(
            Template("page.html", title="List", items=["a", "b", "c"]),
            kida_env=kida_env,
        )
        assert "<li>a</li>" in result.text
        assert "<li>b</li>" in result.text
        assert "<li>c</li>" in result.text

    def test_fragment_rendering(self, kida_env: Environment) -> None:
        result = negotiate(
            Fragment("search.html", "results_list", results=["one", "two"]),
            kida_env=kida_env,
        )
        assert result.status == 200
        assert "text/html" in result.content_type
        assert '<div id="results">' in result.text
        assert "one" in result.text
        assert "two" in result.text
        # Fragment should NOT include the full page wrapper
        assert "<form>" not in result.text
        assert result.render_intent == "fragment"

    def test_page_intent_tracks_fragment_request(self, kida_env: Environment) -> None:
        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"hx-request", b"true")],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )
        result = negotiate(
            Page("search.html", "results_list", results=["one"]),
            kida_env=kida_env,
            request=request,
        )
        assert result.render_intent == "fragment"

    def test_page_composition_renders_fragment(self, kida_env: Environment) -> None:
        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"hx-request", b"true")],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )
        comp = PageComposition(
            template="search.html",
            fragment_block="results_list",
            context={"results": ["a", "b"]},
        )
        result = negotiate(comp, kida_env=kida_env, request=request)
        assert result.render_intent == "fragment"
        assert "a" in result.text
        assert "b" in result.text

    def test_page_composition_renders_full_page(self, kida_env: Environment) -> None:
        comp = PageComposition(
            template="page.html",
            fragment_block="content",
            page_block="content",
            context={"title": "Composed", "items": []},
        )
        result = negotiate(comp, kida_env=kida_env)
        assert result.render_intent == "full_page"
        assert "<title>Composed</title>" in result.text

    def test_page_boosted_request_prefers_page_block_name(self, tmp_path: Path) -> None:
        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        (tmp_path / "base.html").write_text(
            '{% block page_root %}<div class="page-root">{% block panel %}{% endblock %}</div>{% endblock %}'
        )
        (tmp_path / "child.html").write_text(
            '{% extends "base.html" %}{% block panel %}<div id="panel">{{ message }}</div>{% endblock %}'
        )

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [
                    (b"hx-request", b"true"),
                    (b"hx-boosted", b"true"),
                ],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )
        result = negotiate(
            Page("child.html", "panel", page_block_name="page_root", message="Hello"),
            kida_env=env,
            request=request,
        )
        assert result.render_intent == "fragment"
        assert 'class="page-root"' in result.text
        assert 'id="panel"' in result.text
        assert "Hello" in result.text

    def test_template_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(Template("page.html", title="Home"))

    def test_fragment_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(Fragment("search.html", "results"))

    def test_stream_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(Stream("dashboard.html"))

    def test_stream_returns_streaming_response(self, tmp_path: Path) -> None:
        from chirp.http.response import StreamingResponse

        env = Environment(loader=FileSystemLoader(str(tmp_path)))
        (tmp_path / "dash.html").write_text("Hello {{ name }}")
        result = negotiate(Stream("dash.html", name="World"), kida_env=env)
        assert isinstance(result, StreamingResponse)
        assert result.content_type == "text/html; charset=utf-8"
        assert "".join(result.chunks) == "Hello World"

    def test_event_stream_returns_sse_response(self) -> None:
        from chirp.http.response import SSEResponse

        async def gen():
            yield "hello"

        result = negotiate(EventStream(generator=gen()))
        assert isinstance(result, SSEResponse)
        assert result.event_stream.generator is not None

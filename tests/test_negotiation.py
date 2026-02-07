"""Tests for chirp.server.negotiation — content negotiation dispatch."""

import json
from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.response import Redirect, Response
from chirp.realtime.events import EventStream
from chirp.server.negotiation import negotiate
from chirp.templating.returns import Fragment, Stream, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"


@pytest.fixture
def kida_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


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

    def test_template_without_env_raises(self) -> None:
        with pytest.raises(RuntimeError, match="requires kida integration"):
            negotiate(Template("page.html", title="Home"))

    def test_fragment_without_env_raises(self) -> None:
        with pytest.raises(RuntimeError, match="requires kida integration"):
            negotiate(Fragment("search.html", "results"))

    def test_stream_without_env_raises(self) -> None:
        with pytest.raises(RuntimeError, match="requires kida integration"):
            negotiate(Stream("dashboard.html"))

    def test_stream_returns_streaming_response(self, tmp_path) -> None:
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


class TestNegotiatePrimitives:
    def test_string_to_html(self) -> None:
        result = negotiate("Hello, World!")
        assert result.body == "Hello, World!"
        assert "text/html" in result.content_type
        assert result.status == 200

    def test_bytes_to_octet_stream(self) -> None:
        result = negotiate(b"\x00\x01\x02")
        assert result.body == b"\x00\x01\x02"
        assert "octet-stream" in result.content_type

    def test_dict_to_json(self) -> None:
        result = negotiate({"key": "value"})
        assert "application/json" in result.content_type
        parsed = json.loads(result.text)
        assert parsed == {"key": "value"}

    def test_list_to_json(self) -> None:
        result = negotiate([1, 2, 3])
        assert "application/json" in result.content_type
        parsed = json.loads(result.text)
        assert parsed == [1, 2, 3]


class TestNegotiateTuples:
    def test_value_with_status(self) -> None:
        result = negotiate(("Created", 201))
        assert result.status == 201
        assert result.body == "Created"

    def test_dict_with_status(self) -> None:
        result = negotiate(({"id": 1}, 201))
        assert result.status == 201
        assert "application/json" in result.content_type

    def test_value_with_status_and_headers(self) -> None:
        result = negotiate(("Created", 201, {"Location": "/users/42"}))
        assert result.status == 201
        assert ("Location", "/users/42") in result.headers

    def test_template_in_tuple(self, kida_env: Environment) -> None:
        result = negotiate((Template("page.html", title="Created"), 201), kida_env=kida_env)
        assert result.status == 201
        assert "<title>Created</title>" in result.text


class TestNegotiateErrors:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert"):
            negotiate(42)

    def test_error_message_helpful(self) -> None:
        with pytest.raises(TypeError, match="int"):
            negotiate(42)

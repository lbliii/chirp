"""Tests for chirp.server.negotiation — content negotiation dispatch."""

import json
from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.response import Redirect, Response
from chirp.realtime.events import EventStream
from chirp.server.negotiation import negotiate
from chirp.templating.returns import Fragment, OOB, Stream, Template, ValidationError

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


class TestNegotiateValidationError:
    """Tests for ValidationError negotiation — 422 + fragment + optional HX-Retarget."""

    def test_renders_fragment_with_422(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError(
                "form.html", "form_body",
                errors={"email": ["Required"]},
                form={"email": ""},
            ),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert "text/html" in result.content_type
        assert "email: Required" in result.text
        # Should be a fragment, not the full page
        assert "<html>" not in result.text

    def test_without_retarget_has_no_hx_header(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError("form.html", "form_body", errors={}),
            kida_env=kida_env,
        )
        assert result.status == 422
        header_names = {name for name, _ in result.headers}
        assert "HX-Retarget" not in header_names

    def test_with_retarget_sets_header(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError(
                "form.html", "form_errors",
                retarget="#error-banner",
                errors={"email": ["Invalid"]},
            ),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert ("HX-Retarget", "#error-banner") in result.headers
        assert "email: Invalid" in result.text

    def test_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(ValidationError("form.html", "form_body", errors={}))


class TestNegotiateOOB:
    """Tests for OOB multi-fragment out-of-band swap responses."""

    def test_single_oob_fragment(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=["main"]),
                Fragment("cart.html", "counter", count=5),
            ),
            kida_env=kida_env,
        )
        assert result.status == 200
        assert "text/html" in result.content_type
        # Main fragment rendered first
        assert "main" in result.text
        # OOB fragment wrapped with hx-swap-oob
        assert 'hx-swap-oob="true"' in result.text
        assert 'id="counter"' in result.text
        assert "5" in result.text

    def test_multiple_oob_fragments(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=["primary"]),
                Fragment("cart.html", "counter", count=3),
                Fragment("cart.html", "summary", total=7),
            ),
            kida_env=kida_env,
        )
        text = result.text
        # Both OOB fragments present
        assert 'id="counter"' in text
        assert 'id="summary"' in text
        assert text.count('hx-swap-oob="true"') == 2

    def test_oob_uses_block_name_as_default_target(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=[]),
                Fragment("cart.html", "counter", count=0),
            ),
            kida_env=kida_env,
        )
        # block_name "counter" used as target ID
        assert 'id="counter"' in result.text

    def test_oob_explicit_target_overrides_block_name(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=[]),
                Fragment("cart.html", "counter", target="cart-counter", count=0),
            ),
            kida_env=kida_env,
        )
        # Explicit target used instead of block name
        assert 'id="cart-counter"' in result.text
        assert 'id="counter"' not in result.text

    def test_main_as_template(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Template("page.html", title="Full"),
                Fragment("cart.html", "counter", count=1),
            ),
            kida_env=kida_env,
        )
        # Full template rendered as main
        assert "<title>Full</title>" in result.text
        # OOB fragment appended
        assert 'hx-swap-oob="true"' in result.text

    def test_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(OOB(
                Fragment("search.html", "results_list", results=[]),
                Fragment("cart.html", "counter", count=0),
            ))


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


class TestNegotiateEdgeCases:
    """Edge cases for ValidationError and OOB negotiation."""

    def test_validation_error_in_tuple_preserves_422(self, kida_env: Environment) -> None:
        """Wrapping ValidationError in a (value, 422) tuple still returns 422."""
        result = negotiate(
            (ValidationError("form.html", "form_body", errors={"x": ["err"]}), 422),
            kida_env=kida_env,
        )
        assert result.status == 422

    def test_validation_error_tuple_can_override_status(self, kida_env: Environment) -> None:
        """A tuple can override ValidationError's default 422 to another code."""
        result = negotiate(
            (ValidationError("form.html", "form_body", errors={}), 400),
            kida_env=kida_env,
        )
        assert result.status == 400

    def test_oob_with_zero_fragments(self, kida_env: Environment) -> None:
        """OOB with only a main and no OOB fragments renders normally."""
        result = negotiate(
            OOB(Fragment("search.html", "results_list", results=["only"])),
            kida_env=kida_env,
        )
        assert result.status == 200
        assert "only" in result.text
        assert 'hx-swap-oob' not in result.text

    def test_fragment_tuple_422(self, kida_env: Environment) -> None:
        """Plain Fragment in a (value, 422) tuple works for manual validation."""
        result = negotiate(
            (Fragment("search.html", "results_list", results=["err"]), 422),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert "err" in result.text


class TestNegotiateErrors:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert"):
            negotiate(42)

    def test_error_message_helpful(self) -> None:
        with pytest.raises(TypeError, match="int"):
            negotiate(42)

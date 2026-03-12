"""Tests for primitive negotiation (str, bytes, dict, list, tuples, edge cases)."""

import json

from kida import Environment

from chirp.server.negotiation import negotiate
from chirp.templating.returns import OOB, Fragment, Template, ValidationError


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
        assert result.body == b'{"key":"value"}'
        parsed = json.loads(result.text)
        assert parsed == {"key": "value"}

    def test_list_to_json(self) -> None:
        result = negotiate([1, 2, 3])
        assert "application/json" in result.content_type
        assert result.body == b"[1,2,3]"
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
        assert "hx-swap-oob" not in result.text

    def test_fragment_tuple_422(self, kida_env: Environment) -> None:
        """Plain Fragment in a (value, 422) tuple works for manual validation."""
        result = negotiate(
            (Fragment("search.html", "results_list", results=["err"]), 422),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert "err" in result.text

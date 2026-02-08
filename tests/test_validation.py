"""Tests for chirp.validation — composable rules and validate()."""

from chirp.validation import (
    ValidationResult,
    email,
    integer,
    matches,
    max_length,
    min_length,
    number,
    one_of,
    required,
    url,
    validate,
)

# ---------------------------------------------------------------------------
# Individual rule tests
# ---------------------------------------------------------------------------


class TestRequired:
    def test_empty_string(self) -> None:
        assert required("") is not None

    def test_whitespace_only(self) -> None:
        assert required("   ") is not None

    def test_valid(self) -> None:
        assert required("hello") is None


class TestMaxLength:
    def test_within_limit(self) -> None:
        assert max_length(5)("hello") is None

    def test_at_limit(self) -> None:
        assert max_length(5)("12345") is None

    def test_exceeds_limit(self) -> None:
        assert max_length(5)("123456") is not None


class TestMinLength:
    def test_at_minimum(self) -> None:
        assert min_length(3)("abc") is None

    def test_above_minimum(self) -> None:
        assert min_length(3)("abcd") is None

    def test_below_minimum(self) -> None:
        assert min_length(3)("ab") is not None


class TestEmail:
    def test_valid(self) -> None:
        assert email("user@example.com") is None

    def test_valid_with_dots(self) -> None:
        assert email("first.last@sub.domain.org") is None

    def test_missing_at(self) -> None:
        assert email("userexample.com") is not None

    def test_missing_domain(self) -> None:
        assert email("user@") is not None

    def test_empty(self) -> None:
        assert email("") is not None


class TestUrl:
    def test_valid_https(self) -> None:
        assert url("https://example.com") is None

    def test_valid_http(self) -> None:
        assert url("http://example.com/path?q=1") is None

    def test_no_scheme(self) -> None:
        assert url("example.com") is not None

    def test_ftp_rejected(self) -> None:
        assert url("ftp://example.com") is not None


class TestMatches:
    def test_valid_pattern(self) -> None:
        assert matches(r"^\d{3}$")("123") is None

    def test_invalid_pattern(self) -> None:
        assert matches(r"^\d{3}$")("12") is not None

    def test_custom_message(self) -> None:
        error = matches(r"^\d+$", message="Numbers only")("abc")
        assert error == "Numbers only"


class TestOneOf:
    def test_valid_choice(self) -> None:
        assert one_of("red", "green", "blue")("red") is None

    def test_invalid_choice(self) -> None:
        assert one_of("red", "green", "blue")("purple") is not None


class TestInteger:
    def test_valid(self) -> None:
        assert integer("42") is None

    def test_negative(self) -> None:
        assert integer("-7") is None

    def test_invalid(self) -> None:
        assert integer("abc") is not None

    def test_float_rejected(self) -> None:
        assert integer("3.14") is not None


class TestNumber:
    def test_integer(self) -> None:
        assert number("42") is None

    def test_float(self) -> None:
        assert number("3.14") is None

    def test_invalid(self) -> None:
        assert number("abc") is not None


# ---------------------------------------------------------------------------
# validate() integration tests
# ---------------------------------------------------------------------------


class TestValidate:
    def test_all_valid(self) -> None:
        data = {"name": "alice", "age": "30"}
        result = validate(
            data,
            {
                "name": [required, max_length(50)],
                "age": [required, integer],
            },
        )
        assert result.is_valid
        assert result.data == {"name": "alice", "age": "30"}
        assert result.errors == {}

    def test_single_field_error(self) -> None:
        data = {"name": "", "age": "30"}
        result = validate(
            data,
            {
                "name": [required],
                "age": [required],
            },
        )
        assert not result.is_valid
        assert "name" in result.errors
        assert "age" not in result.errors
        assert result.data == {"age": "30"}

    def test_multiple_field_errors(self) -> None:
        data = {"name": "", "email": "bad"}
        result = validate(
            data,
            {
                "name": [required],
                "email": [required, email],
            },
        )
        assert not result.is_valid
        assert "name" in result.errors
        assert "email" in result.errors

    def test_missing_field_treated_as_empty(self) -> None:
        data: dict[str, str] = {}
        result = validate(
            data,
            {
                "title": [required],
            },
        )
        assert not result.is_valid
        assert "title" in result.errors

    def test_required_stops_chain(self) -> None:
        """If required fails, subsequent validators are skipped."""
        data = {"name": ""}
        result = validate(
            data,
            {
                "name": [required, min_length(5)],
            },
        )
        # Only the required error, not min_length
        assert len(result.errors["name"]) == 1

    def test_multiple_errors_per_field(self) -> None:
        """Non-required validators all run and collect errors."""
        data = {"code": "x"}
        result = validate(
            data,
            {
                "code": [min_length(3), matches(r"^\d+$")],
            },
        )
        assert len(result.errors["code"]) == 2

    def test_bool_falsy_when_invalid(self) -> None:
        result = validate({}, {"x": [required]})
        assert not result
        assert bool(result) is False

    def test_bool_truthy_when_valid(self) -> None:
        result = validate({"x": "value"}, {"x": [required]})
        assert result
        assert bool(result) is True

    def test_custom_validator(self) -> None:
        def no_spaces(value: str) -> str | None:
            if " " in value:
                return "Must not contain spaces"
            return None

        data = {"username": "has space"}
        result = validate(
            data,
            {
                "username": [required, no_spaces],
            },
        )
        assert not result.is_valid
        assert "spaces" in result.errors["username"][0]

    def test_with_form_data(self) -> None:
        """validate() works with FormData (MultiValueMapping)."""
        from chirp.http.forms import FormData

        form = FormData({"name": ["alice"], "email": ["alice@example.com"]})
        result = validate(
            form,
            {
                "name": [required],
                "email": [required, email],
            },
        )
        assert result.is_valid
        assert result.data["name"] == "alice"


class TestValidationResult:
    def test_is_valid_no_errors(self) -> None:
        r = ValidationResult(data={"x": "1"}, errors={})
        assert r.is_valid is True

    def test_is_valid_with_errors(self) -> None:
        r = ValidationResult(data={}, errors={"x": ["bad"]})
        assert r.is_valid is False

    def test_frozen(self) -> None:
        r = ValidationResult(data={}, errors={})
        import pytest

        with pytest.raises(AttributeError):
            r.data = {}  # type: ignore[misc]

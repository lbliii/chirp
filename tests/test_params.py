"""Tests for chirp.routing.params — path parameter conversion."""

import pytest

from chirp.routing.params import CONVERTERS, convert_param


class TestConverters:
    def test_all_types_registered(self) -> None:
        assert set(CONVERTERS) == {"str", "int", "float", "path"}

    def test_str_regex_excludes_slash(self) -> None:
        pattern, _ = CONVERTERS["str"]
        assert "/" not in pattern or pattern == r"[^/]+"

    def test_path_regex_matches_slashes(self) -> None:
        pattern, _ = CONVERTERS["path"]
        assert pattern == r".+"


class TestConvertParam:
    def test_str_passthrough(self) -> None:
        assert convert_param("hello", "str") == "hello"
        assert isinstance(convert_param("hello", "str"), str)

    def test_int_conversion(self) -> None:
        assert convert_param("42", "int") == 42
        assert isinstance(convert_param("42", "int"), int)

    def test_float_conversion(self) -> None:
        assert convert_param("3.14", "float") == pytest.approx(3.14)
        assert isinstance(convert_param("3.14", "float"), float)

    def test_float_from_integer_string(self) -> None:
        assert convert_param("10", "float") == 10.0

    def test_path_passthrough(self) -> None:
        assert convert_param("docs/api/v2", "path") == "docs/api/v2"

    def test_int_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            convert_param("abc", "int")

    def test_float_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            convert_param("abc", "float")

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(KeyError):
            convert_param("value", "uuid")

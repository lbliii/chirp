"""Tests for chirp.http.query — immutable QueryParams."""

import pytest

from chirp._internal.multimap import MultiValueMapping
from chirp.http.query import QueryParams


class TestQueryParams:
    def test_getitem(self) -> None:
        q = QueryParams(b"q=hello&page=2")
        assert q["q"] == "hello"
        assert q["page"] == "2"

    def test_missing_key_raises(self) -> None:
        q = QueryParams(b"q=hello")
        with pytest.raises(KeyError):
            q["missing"]

    def test_contains(self) -> None:
        q = QueryParams(b"q=hello")
        assert "q" in q
        assert "missing" not in q

    def test_len(self) -> None:
        q = QueryParams(b"a=1&b=2&c=3")
        assert len(q) == 3

    def test_iter(self) -> None:
        q = QueryParams(b"a=1&b=2")
        assert set(q) == {"a", "b"}

    def test_get_with_default(self) -> None:
        q = QueryParams(b"q=hello")
        assert q.get("q") == "hello"
        assert q.get("missing") is None
        assert q.get("missing", "fallback") == "fallback"

    def test_get_list(self) -> None:
        q = QueryParams(b"tag=python&tag=rust&q=hello")
        assert q.get_list("tag") == ["python", "rust"]
        assert q.get_list("q") == ["hello"]
        assert q.get_list("missing") == []

    def test_get_int(self) -> None:
        q = QueryParams(b"page=3&size=abc")
        assert q.get_int("page") == 3
        assert q.get_int("size") is None  # not numeric
        assert q.get_int("missing") is None
        assert q.get_int("missing", 10) == 10

    def test_get_bool(self) -> None:
        q = QueryParams(b"a=true&b=1&c=yes&d=on&e=false&f=0")
        assert q.get_bool("a") is True
        assert q.get_bool("b") is True
        assert q.get_bool("c") is True
        assert q.get_bool("d") is True
        assert q.get_bool("e") is False
        assert q.get_bool("f") is False
        assert q.get_bool("missing") is None
        assert q.get_bool("missing", False) is False

    def test_empty(self) -> None:
        q = QueryParams(b"")
        assert len(q) == 0
        assert list(q) == []

    def test_blank_value_preserved(self) -> None:
        q = QueryParams(b"flag=")
        assert q["flag"] == ""

    def test_first_value_returned(self) -> None:
        q = QueryParams(b"x=first&x=second")
        assert q["x"] == "first"

    def test_satisfies_multivalue_mapping(self) -> None:
        q = QueryParams(b"a=1")
        assert isinstance(q, MultiValueMapping)

    def test_repr(self) -> None:
        q = QueryParams(b"q=hello")
        assert "hello" in repr(q)

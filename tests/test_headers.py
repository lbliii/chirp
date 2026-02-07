"""Tests for chirp.http.headers — immutable, case-insensitive Headers."""

import pytest

from chirp._internal.multimap import MultiValueMapping
from chirp.http.headers import Headers


def _h(*pairs: tuple[str, str]) -> Headers:
    """Shorthand: build Headers from string pairs."""
    raw = tuple((k.encode("latin-1"), v.encode("latin-1")) for k, v in pairs)
    return Headers(raw)


class TestHeaders:
    def test_getitem(self) -> None:
        h = _h(("Content-Type", "text/html"))
        assert h["Content-Type"] == "text/html"

    def test_case_insensitive(self) -> None:
        h = _h(("Content-Type", "text/html"))
        assert h["content-type"] == "text/html"
        assert h["CONTENT-TYPE"] == "text/html"

    def test_missing_key_raises(self) -> None:
        h = _h(("Accept", "*/*"))
        with pytest.raises(KeyError):
            h["X-Missing"]

    def test_contains(self) -> None:
        h = _h(("Accept", "*/*"))
        assert "accept" in h
        assert "Accept" in h
        assert "x-missing" not in h

    def test_contains_rejects_non_str(self) -> None:
        h = _h(("Accept", "*/*"))
        assert 42 not in h  # type: ignore[operator]

    def test_len(self) -> None:
        h = _h(("A", "1"), ("B", "2"), ("C", "3"))
        assert len(h) == 3

    def test_len_deduplicates(self) -> None:
        h = _h(("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"))
        assert len(h) == 1  # one unique key

    def test_iter_yields_unique_lowercase_keys(self) -> None:
        h = _h(("Accept", "*/*"), ("Content-Type", "text/html"), ("Accept", "text/xml"))
        keys = list(h)
        assert keys == ["accept", "content-type"]

    def test_get_with_default(self) -> None:
        h = _h(("Accept", "*/*"))
        assert h.get("accept") == "*/*"
        assert h.get("x-missing") is None
        assert h.get("x-missing", "fallback") == "fallback"

    def test_get_list(self) -> None:
        h = _h(("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("Accept", "*/*"))
        assert h.get_list("Set-Cookie") == ["a=1", "b=2"]
        assert h.get_list("Accept") == ["*/*"]
        assert h.get_list("X-Missing") == []

    def test_raw_property(self) -> None:
        raw = ((b"a", b"1"), (b"b", b"2"))
        h = Headers(raw)
        assert h.raw is raw

    def test_empty_headers(self) -> None:
        h = Headers()
        assert len(h) == 0
        assert list(h) == []

    def test_satisfies_multivalue_mapping(self) -> None:
        h = _h(("A", "1"))
        assert isinstance(h, MultiValueMapping)

    def test_repr(self) -> None:
        h = _h(("Accept", "*/*"))
        assert "accept" in repr(h)

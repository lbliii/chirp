"""Immutable query string parameters.

Implements ``Mapping[str, str]`` and the ``MultiValueMapping`` protocol.
"""

from collections.abc import Iterator, Mapping
from urllib.parse import parse_qs


class QueryParams(Mapping[str, str]):
    """Immutable query string parameters.

    Attributes:
        _data: Parsed query string as field name -> list of values.
        _raw: Raw query string bytes.

    ``__getitem__`` returns the first value for a key.
    ``get_list`` returns all values for a key.
    """

    _data: dict[str, list[str]]
    _raw: bytes

    __slots__ = ("_data", "_raw")

    def __init__(self, query_string: bytes = b"") -> None:
        object.__setattr__(self, "_raw", query_string)
        parsed = parse_qs(query_string.decode("latin-1"), keep_blank_values=True)
        object.__setattr__(self, "_data", parsed)

    def __getitem__(self, key: str) -> str:
        return self._data[key][0]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        items = ", ".join(f"{k!r}: {self[k]!r}" for k in self)
        return f"QueryParams({{{items}}})"

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        """Return the first value for *key*, or *default* if missing."""
        values = self._data.get(key)
        if values:
            return values[0]
        return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for *key*."""
        return list(self._data.get(key, []))

    def get_int(self, key: str, default: int | None = None) -> int | None:
        """Return value as int, or *default* if missing or not numeric."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool | None = None) -> bool | None:
        """Return value as bool (``true``/``1``/``yes``/``on`` → True)."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

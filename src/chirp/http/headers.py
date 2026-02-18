"""Immutable, case-insensitive HTTP headers.

Implements ``Mapping[str, str]`` and the ``MultiValueMapping`` protocol.
Stores raw byte pairs from the ASGI scope; decodes on access.
"""

from collections.abc import Iterator, Mapping


class Headers(Mapping[str, str]):
    """Immutable, case-insensitive HTTP headers.

    ``__getitem__`` returns the first matching value.
    ``get_list`` returns all values for a header (e.g. multiple ``Set-Cookie``).
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: tuple[tuple[bytes, bytes], ...] = ()) -> None:
        object.__setattr__(self, "_raw", raw)

    def __getitem__(self, key: str) -> str:
        key_lower = key.lower().encode("latin-1")
        for name, value in self._raw:
            if name.lower() == key_lower:
                return value.decode("latin-1")
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        key_lower = key.lower().encode("latin-1")
        return any(name.lower() == key_lower for name, _ in self._raw)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for name, _ in self._raw:
            key = name.decode("latin-1").lower()
            if key not in seen:
                seen.add(key)
                yield key

    def __len__(self) -> int:
        return len(set(self))

    def __repr__(self) -> str:
        items = ", ".join(f"{k!r}: {self[k]!r}" for k in self)
        return f"Headers({{{items}}})"

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        """Return the first value for *key*, or *default* if missing."""
        try:
            return self[key]
        except KeyError:
            return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for *key* (e.g. multiple ``Set-Cookie``)."""
        key_lower = key.lower().encode("latin-1")
        return [value.decode("latin-1") for name, value in self._raw if name.lower() == key_lower]

    @property
    def raw(self) -> tuple[tuple[bytes, bytes], ...]:
        """Access raw header byte pairs for ASGI compatibility."""
        return self._raw

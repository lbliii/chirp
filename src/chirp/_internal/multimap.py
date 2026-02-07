"""MultiValueMapping protocol — shared interface for Headers, QueryParams, FormData.

A structural protocol so middleware and utilities can accept any
multi-valued mapping without coupling to the concrete type.
"""

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class MultiValueMapping(Protocol):
    """A read-only string mapping where keys can have multiple values.

    ``__getitem__`` returns the first value for a key.
    ``get_list`` returns all values for a key.

    Structurally compatible with ``Mapping[str, str]`` plus ``get_list``.
    Defined with explicit dunder methods because Python 3.14 Protocols
    cannot inherit from non-Protocol ABCs like ``Mapping``.
    """

    def __getitem__(self, key: str) -> str: ...
    def __contains__(self, key: object) -> bool: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def get_list(self, key: str) -> list[str]: ...

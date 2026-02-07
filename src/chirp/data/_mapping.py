"""Row-to-dataclass mapping.

Converts raw database rows (tuples or dicts) into typed frozen dataclasses.
Uses dataclass field introspection — no metaclass magic, no descriptors.
"""

import dataclasses
from typing import Any


def map_row[T](cls: type[T], row: dict[str, Any]) -> T:
    """Map a dict-like row to a frozen dataclass instance.

    Only passes keys that match dataclass fields. Extra columns are silently
    ignored (SELECT * is fine even if the dataclass has fewer fields).

    Raises ``TypeError`` if required fields are missing from the row.
    """
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — chirp.data requires frozen dataclasses"
        raise TypeError(msg)

    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in row.items() if k in field_names}
    return cls(**filtered)


def map_rows[T](cls: type[T], rows: list[dict[str, Any]]) -> list[T]:
    """Map a list of dict-like rows to frozen dataclass instances."""
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — chirp.data requires frozen dataclasses"
        raise TypeError(msg)

    field_names = {f.name for f in dataclasses.fields(cls)}
    return [cls(**{k: v for k, v in row.items() if k in field_names}) for row in rows]

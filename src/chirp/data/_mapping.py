"""Row-to-dataclass mapping with type coercion.

Converts raw database rows (tuples or dicts) into typed frozen dataclasses.
Uses dataclass field introspection — no metaclass magic, no descriptors.

Type coercion handles the mismatch between database drivers (SQLite returns
strings for some column types) and Python dataclass annotations. Fields
annotated as ``int`` will coerce string values like ``"45"`` to ``45``,
and empty strings to ``0``.
"""

import dataclasses
import types
from typing import Any, get_args, get_origin


# Scalar types we know how to coerce from database driver values.
_COERCIBLE: dict[type, Any] = {
    int: lambda v: int(v) if v != "" else 0,
    float: lambda v: float(v) if v != "" else 0.0,
    bool: lambda v: bool(int(v)) if isinstance(v, str) else bool(v),
    str: str,
}


def _build_coercion_map(cls: type) -> dict[str, type | None]:
    """Build a {field_name: target_type} map for coercible fields.

    Returns ``None`` for fields that don't need coercion (complex types,
    generics, etc.).
    """
    result: dict[str, type | None] = {}
    for f in dataclasses.fields(cls):
        annotation = f.type
        # Unwrap Optional (X | None) — coerce to the non-None branch
        origin = get_origin(annotation)
        if origin is types.UnionType:
            args = [a for a in get_args(annotation) if a is not type(None)]
            annotation = args[0] if len(args) == 1 else None
        result[f.name] = annotation if annotation in _COERCIBLE else None
    return result


def _coerce(value: Any, target: type | None) -> Any:
    """Coerce a single value to the target type, if needed."""
    if target is None or value is None or isinstance(value, target):
        return value
    return _COERCIBLE[target](value)


def map_row[T](cls: type[T], row: dict[str, Any]) -> T:
    """Map a dict-like row to a frozen dataclass instance.

    Only passes keys that match dataclass fields. Extra columns are silently
    ignored (SELECT * is fine even if the dataclass has fewer fields).

    Values are coerced to match field annotations: ``int``, ``float``,
    ``bool``, and ``str`` fields handle driver type mismatches automatically.
    Empty strings in ``int``/``float`` columns coerce to ``0``/``0.0``.

    Raises ``TypeError`` if required fields are missing from the row.
    """
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — chirp.data requires frozen dataclasses"
        raise TypeError(msg)

    coercion = _build_coercion_map(cls)
    filtered = {
        k: _coerce(v, coercion.get(k))
        for k, v in row.items()
        if k in coercion
    }
    return cls(**filtered)


def map_rows[T](cls: type[T], rows: list[dict[str, Any]]) -> list[T]:
    """Map a list of dict-like rows to frozen dataclass instances."""
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — chirp.data requires frozen dataclasses"
        raise TypeError(msg)

    coercion = _build_coercion_map(cls)
    field_names = set(coercion)
    return [
        cls(**{k: _coerce(v, coercion.get(k)) for k, v in row.items() if k in field_names})
        for row in rows
    ]

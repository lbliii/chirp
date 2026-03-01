"""Typed extraction of query parameters and form/JSON body data.

Automatically populates frozen dataclass instances from request data,
converting string values to the annotated field types.  Used by the
handler resolution system when a parameter's type annotation is a
dataclass.

Resolution rules (by HTTP method):

- **GET / HEAD**: extract from query string
- **POST / PUT / PATCH / DELETE**: extract from form body or JSON body
  (based on Content-Type header)

Supported field types: ``str``, ``int``, ``float``, ``bool``.
Missing keys use the dataclass field default.  Type conversion
failures also fall back to the default.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any


def is_extractable_dataclass(annotation: Any) -> bool:
    """Return True if *annotation* is a user-defined dataclass type.

    Excludes chirp's own dataclass types (``Request``, ``Response``, etc.)
    which should never be auto-extracted from query/form data.
    """
    if not isinstance(annotation, type) or not dataclasses.is_dataclass(annotation):
        return False

    # Exclude chirp's internal dataclass types by module prefix
    module = getattr(annotation, "__module__", "") or ""
    return not module.startswith("chirp.")


def extract_dataclass[T](cls: type[T], data: Mapping[str, Any]) -> T:
    """Create a dataclass instance from a mapping (query params, form, JSON).

    For each field in *cls*, looks up the field name in *data*.  If found,
    converts the value to the field's annotated type.  If missing or
    conversion fails, uses the field's default value.

    Args:
        cls: A dataclass type to instantiate.
        data: A mapping of string keys to values (query params, form data,
            or parsed JSON).

    Returns:
        A new instance of *cls* populated from *data*.
    """
    kwargs: dict[str, Any] = {}

    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue

        raw = data[f.name]
        target_type = f.type

        # Resolve string annotations to actual types
        if isinstance(target_type, str):
            target_type = _resolve_type(target_type)

        kwargs[f.name] = _convert(raw, target_type)

    return cls(**kwargs)


def _convert(value: Any, target_type: Any) -> Any:
    """Convert *value* to *target_type*, returning *value* unchanged on failure."""
    if target_type is str:
        s = str(value)
        return s.strip() if isinstance(value, str) else s

    if target_type is int:
        try:
            return int(value)
        except ValueError, TypeError:
            return value

    if target_type is float:
        try:
            return float(value)
        except ValueError, TypeError:
            return value

    if target_type is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    # Unknown type — return raw value
    return value


def _resolve_type(name: str) -> type | str:
    """Resolve common type names from string annotations."""
    _builtins: dict[str, type] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }
    return _builtins.get(name, name)

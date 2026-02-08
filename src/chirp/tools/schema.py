"""Function signature to JSON Schema conversion.

Inspects a function's type annotations and produces an MCP-compatible
JSON Schema for the ``inputSchema`` field of ``tools/list`` responses.

Adapted from ``chirp.ai._structured.dataclass_to_schema`` but operates
on function parameters instead of dataclass fields.
"""

import inspect
import types
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin

from chirp.http.request import Request

# Python type → JSON Schema type
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def function_to_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate MCP-compatible JSON Schema from a function's type annotations.

    Parameters named ``request`` or annotated as ``Request`` are excluded
    (same convention as chirp route handlers).

    Parameters with defaults are optional (not in ``required``).
    ``X | None`` unions are unwrapped to the base type.

    Supports: ``str``, ``int``, ``float``, ``bool``, ``list[str]``,
    ``list[int]``, ``list[float]``, ``X | None``.
    """
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        # Skip request injection (same convention as route handlers)
        if name == "request" or param.annotation is Request:
            continue

        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            # Unannotated params default to string
            annotation = str

        # Unwrap X | None → X (optional param)
        is_optional = _is_optional(annotation)
        if is_optional:
            annotation = _unwrap_optional(annotation)

        schema = _type_to_schema(annotation)

        # Add description from docstring if available (future enhancement)
        properties[name] = schema

        # Required unless it has a default value or is Optional
        has_default = param.default is not inspect.Parameter.empty
        if not has_default and not is_optional:
            required.append(name)

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        result["required"] = required
    return result


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    # Handle basic types
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    # Handle list[X] (generic alias)
    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        if args and args[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[args[0]]}}
        return {"type": "array"}

    # Handle dict[str, X]
    if origin is dict:
        return {"type": "object"}

    # Fallback
    return {"type": "string"}


def _is_optional(annotation: Any) -> bool:
    """Check if an annotation is X | None."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        return type(None) in args
    return False


def _unwrap_optional(annotation: Any) -> Any:
    """Extract the non-None type from X | None."""
    args = get_args(annotation)
    non_none = [a for a in args if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    # Multi-type union — fall back to string
    return str

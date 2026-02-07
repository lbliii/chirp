"""Structured output — LLM JSON responses to frozen dataclasses.

Generates JSON schema from dataclass fields and parses LLM responses
back into typed instances. Same pattern as chirp.data row mapping —
both produce frozen dataclasses from external data.
"""

import dataclasses
import json
from typing import Any

from chirp.ai.errors import StructuredOutputError

# Python type → JSON schema type
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def dataclass_to_schema[T](cls: type[T]) -> dict[str, Any]:
    """Generate a JSON schema from a frozen dataclass.

    Used to instruct the LLM to return structured output matching
    the dataclass fields.

    Supports: str, int, float, bool, list[str], list[int], list[float].
    """
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — structured output requires frozen dataclasses"
        raise TypeError(msg)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in dataclasses.fields(cls):
        schema = _type_to_schema(field.type)
        properties[field.name] = schema
        # All fields are required unless they have a default
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            required.append(field.name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON schema fragment."""
    # Handle basic types
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    # Handle list[X] (generic alias)
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        args = getattr(annotation, "__args__", ())
        if args and args[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[args[0]]}}
        return {"type": "array"}

    # Fallback
    return {"type": "string"}


def parse_structured[T](cls: type[T], text: str) -> T:
    """Parse an LLM text response into a frozen dataclass.

    Extracts JSON from the response text (handles markdown code fences)
    and maps it to the dataclass fields.
    """
    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        msg = f"Failed to parse LLM response as JSON: {exc}"
        raise StructuredOutputError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Expected JSON object, got {type(data).__name__}"
        raise StructuredOutputError(msg)

    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in field_names}

    try:
        return cls(**filtered)
    except TypeError as exc:
        msg = f"Failed to construct {cls.__name__} from LLM response: {exc}"
        raise StructuredOutputError(msg) from exc


def _extract_json(text: str) -> str:
    """Extract JSON from LLM text, handling markdown code fences."""
    stripped = text.strip()

    # Try direct parse first
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    # Handle ```json ... ``` fences
    if "```json" in stripped:
        start = stripped.index("```json") + 7
        end = stripped.index("```", start)
        return stripped[start:end].strip()

    # Handle ``` ... ``` fences
    if "```" in stripped:
        start = stripped.index("```") + 3
        end = stripped.index("```", start)
        return stripped[start:end].strip()

    # Last resort — find first { to last }
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end != -1:
        return stripped[brace_start : brace_end + 1]

    msg = "No JSON found in LLM response"
    raise StructuredOutputError(msg)

"""Structured output — LLM JSON responses to typed models.

Generates JSON schema from dataclass fields or Pydantic models and parses
LLM responses back into typed instances.
"""

from __future__ import annotations

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


def is_structured_type(cls: type[Any]) -> bool:
    """Return True if *cls* is a supported structured-output target."""
    if dataclasses.is_dataclass(cls):
        return True
    return _is_pydantic_model(cls)


def schema_for_type(cls: type[Any]) -> dict[str, Any]:
    """Generate a JSON schema for a dataclass or Pydantic model."""
    if dataclasses.is_dataclass(cls):
        return dataclass_to_schema(cls)
    if _is_pydantic_model(cls):
        return pydantic_to_schema(cls)
    msg = (
        f"{getattr(cls, '__name__', cls)!r} is not a dataclass or Pydantic model — "
        "structured output requires frozen dataclasses or pydantic.BaseModel subclasses"
    )
    raise TypeError(msg)


def dataclass_to_schema[T](cls: type[T]) -> dict[str, Any]:
    """Generate a JSON schema from a frozen dataclass."""
    if not dataclasses.is_dataclass(cls):
        msg = f"{cls.__name__} is not a dataclass — structured output requires frozen dataclasses"
        raise TypeError(msg)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in dataclasses.fields(cls):
        schema = _type_to_schema(field.type)
        properties[field.name] = schema
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            required.append(field.name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def pydantic_to_schema(cls: type[Any]) -> dict[str, Any]:
    """Generate a JSON schema from a Pydantic ``BaseModel`` subclass."""
    if not _is_pydantic_model(cls):
        msg = f"{cls.__name__} is not a Pydantic BaseModel"
        raise TypeError(msg)

    schema = cls.model_json_schema()
    return _inline_json_schema(schema)


def parse_structured[T](cls: type[T], text: str) -> T:
    """Parse an LLM text response into a dataclass or Pydantic model."""
    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        msg = f"Failed to parse LLM response as JSON: {exc}"
        raise StructuredOutputError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Expected JSON object, got {type(data).__name__}"
        raise StructuredOutputError(msg)

    if _is_pydantic_model(cls):
        try:
            return cls.model_validate(data)  # type: ignore[union-attr,no-any-return]
        except Exception as exc:
            msg = f"Failed to construct {cls.__name__} from LLM response: {exc}"
            raise StructuredOutputError(msg) from exc

    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in field_names}

    try:
        return cls(**filtered)
    except TypeError as exc:
        msg = f"Failed to construct {cls.__name__} from LLM response: {exc}"
        raise StructuredOutputError(msg) from exc


def structured_repair_prompt(*, error: StructuredOutputError, bad_text: str) -> str:
    """Build a follow-up user message asking the model to repair bad JSON."""
    snippet = bad_text.strip()
    if len(snippet) > 500:
        snippet = snippet[:500] + "…"
    return (
        "Your previous response could not be parsed as valid JSON matching the schema.\n"
        f"Parse error: {error}\n"
        f"Previous response:\n{snippet}\n\n"
        "Return ONLY a corrected JSON object matching the schema. No other text."
    )


def _is_pydantic_model(cls: type[Any]) -> bool:
    try:
        from pydantic import BaseModel
    except ImportError:
        return False
    return isinstance(cls, type) and issubclass(cls, BaseModel)


def _inline_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Pydantic ``$defs`` schema into a single object schema."""
    defs = schema.get("$defs", {})
    return _resolve_schema_refs(schema, defs)


def _resolve_schema_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#/$defs/"):
                key = ref.removeprefix("#/$defs/")
                if key in defs:
                    return _resolve_schema_refs(defs[key], defs)
            return node
        resolved = {k: _resolve_schema_refs(v, defs) for k, v in node.items() if k != "$defs"}
        if resolved.get("type") == "object" and "additionalProperties" not in resolved:
            resolved["additionalProperties"] = False
        return resolved
    if isinstance(node, list):
        return [_resolve_schema_refs(item, defs) for item in node]
    return node


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON schema fragment."""
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        args = getattr(annotation, "__args__", ())
        if args and args[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[args[0]]}}
        return {"type": "array"}

    return {"type": "string"}


def _extract_json(text: str) -> str:
    """Extract JSON from LLM text, handling markdown code fences."""
    stripped = text.strip()

    if stripped.startswith(("{", "[")):
        return stripped

    if "```json" in stripped:
        start = stripped.index("```json") + 7
        end = stripped.index("```", start)
        return stripped[start:end].strip()

    if "```" in stripped:
        start = stripped.index("```") + 3
        end = stripped.index("```", start)
        return stripped[start:end].strip()

    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end != -1:
        return stripped[brace_start : brace_end + 1]

    msg = "No JSON found in LLM response"
    raise StructuredOutputError(msg)

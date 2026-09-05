"""Validate the JSON Schema vocabulary emitted for Chirp tool parameters."""

from typing import Any


class ToolArgumentsError(TypeError):
    """Arguments violate a tool schema; safe to report to the MCP caller."""


def validate_arguments(name: str, arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    """Reject schema-invalid input before dispatch without coercing arguments.

    Covers the types, properties, required fields, unions, and array items emitted by
    ``function_to_schema``. Additional properties remain allowed, as advertised.
    Error messages identify the tool and parameter without echoing input values.
    """
    _validate(arguments, schema, f"Tool {name!r} arguments")


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    if "anyOf" in schema:
        errors = []
        for variant in schema["anyOf"]:
            try:
                _validate(value, variant, path)
            except ToolArgumentsError as exc:
                errors.append(str(exc))
            else:
                break
        else:
            msg = "No matching argument schema: " + "; or ".join(errors)
            raise ToolArgumentsError(msg)

    expected = schema.get("type")
    match expected:
        case "string":
            valid = isinstance(value, str)
        case "integer":
            valid = not isinstance(value, bool) and (
                isinstance(value, int) or (isinstance(value, float) and value.is_integer())
            )
        case "number":
            valid = isinstance(value, int | float) and not isinstance(value, bool)
        case "boolean":
            valid = isinstance(value, bool)
        case "array":
            valid = isinstance(value, list)
        case "object":
            valid = isinstance(value, dict)
        case _:
            valid = True
    if not valid:
        msg = f"{path}: expected {expected}"
        raise ToolArgumentsError(msg)

    if isinstance(value, dict):
        for field in schema.get("required", []):
            if field not in value:
                msg = f"{path}[{field!r}]: required argument is missing"
                raise ToolArgumentsError(msg)
        for field, field_schema in schema.get("properties", {}).items():
            if field in value:
                _validate(value[field], field_schema, f"{path}[{field!r}]")
    elif isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")

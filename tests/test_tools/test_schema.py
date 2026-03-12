"""Tests for chirp.tools.schema — function_to_schema."""

from typing import Any

import pytest

from chirp.http.request import Request
from chirp.tools.schema import function_to_schema


class TestFunctionToSchema:
    def test_no_params(self) -> None:
        def func() -> str:
            return "hello"

        schema = function_to_schema(func)
        assert schema == {"type": "object", "properties": {}}

    def test_basic_types(self) -> None:
        def func(name: str, count: int, rate: float, active: bool) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["count"] == {"type": "integer"}
        assert schema["properties"]["rate"] == {"type": "number"}
        assert schema["properties"]["active"] == {"type": "boolean"}
        assert sorted(schema["required"]) == ["active", "count", "name", "rate"]

    def test_optional_with_default(self) -> None:
        def func(query: str, limit: int = 10) -> None:
            pass

        schema = function_to_schema(func)
        assert "query" in schema["required"]
        assert "limit" not in schema.get("required", [])

    def test_optional_union_none(self) -> None:
        def func(query: str, category: str | None = None) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["category"] == {"type": "string"}
        assert "category" not in schema.get("required", [])

    def test_list_type(self) -> None:
        def func(tags: list[str]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}

    def test_list_int(self) -> None:
        def func(ids: list[int]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["ids"] == {"type": "array", "items": {"type": "integer"}}

    def test_dict_type(self) -> None:
        def func(metadata: dict[str, Any]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["metadata"] == {"type": "object"}

    def test_request_param_excluded(self) -> None:
        """Parameters named 'request' or annotated as Request are excluded."""

        def func(request: Request, query: str) -> None:
            pass

        schema = function_to_schema(func)
        assert "request" not in schema["properties"]
        assert "query" in schema["properties"]

    def test_request_by_name_excluded(self) -> None:
        def func(request: Any, query: str) -> None:
            pass

        schema = function_to_schema(func)
        assert "request" not in schema["properties"]

    def test_unannotated_defaults_to_string(self) -> None:
        def func(name) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"] == {"type": "string"}

    def test_async_function(self) -> None:
        async def func(query: str, limit: int = 10) -> list[dict]:
            return []

        schema = function_to_schema(func)
        assert schema["properties"]["query"] == {"type": "string"}
        assert schema["properties"]["limit"] == {"type": "integer"}
        assert schema["required"] == ["query"]

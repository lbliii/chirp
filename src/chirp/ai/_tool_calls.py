"""Provider-neutral tool-call normalization for LLM adapters."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from chirp.tools.registry import McpToolInfo, ToolRegistry


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """Normalized completion from a provider message response."""

    content: str
    tool_calls: tuple[dict[str, Any], ...]
    assistant_message: dict[str, Any]


def tools_from_registry(registry: ToolRegistry | None) -> list[McpToolInfo]:
    if registry is None:
        return []
    return registry.list_tools()


def tools_to_openai(tools: Sequence[McpToolInfo]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in tools
    ]


def tools_to_anthropic(tools: Sequence[McpToolInfo]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["inputSchema"],
        }
        for t in tools
    ]


def parse_openai_completion(data: dict[str, Any]) -> ChatCompletion:
    message = data["choices"][0]["message"]
    content = message.get("content") or ""
    raw_calls = message.get("tool_calls") or ()
    tool_calls: list[dict[str, Any]] = []
    for call in raw_calls:
        func = call.get("function", {})
        args_raw = func.get("arguments") or "{}"
        if isinstance(args_raw, str):
            try:
                arguments = json.loads(args_raw)
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = args_raw
        tool_calls.append(
            {
                "call_id": call.get("id", ""),
                "name": func.get("name", ""),
                "arguments": arguments,
            }
        )
    assistant_message = dict(message)
    return ChatCompletion(
        content=content,
        tool_calls=tuple(tool_calls),
        assistant_message=assistant_message,
    )


def parse_anthropic_completion(data: dict[str, Any]) -> ChatCompletion:
    blocks = data.get("content") or []
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    assistant_blocks: list[dict[str, Any]] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(block.get("text", ""))
            assistant_blocks.append(block)
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "call_id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": block.get("input") or {},
                }
            )
            assistant_blocks.append(block)
    assistant_message = {"role": "assistant", "content": assistant_blocks}
    return ChatCompletion(
        content="".join(text_parts),
        tool_calls=tuple(tool_calls),
        assistant_message=assistant_message,
    )


def tool_result_message_openai(call_id: str, content: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def tool_result_message_anthropic(call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": call_id, "content": content}],
    }


def format_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)

"""Thin httpx wrapper for the Ollama chat API.

Two methods:

- ``chat()`` — non-streaming, used during tool-calling rounds
- ``chat_stream()`` — streaming, used for the final answer

Schema conversion translates chirp's MCP tool format into Ollama's
function-calling format. The shapes are nearly identical — just a
thin wrapper around ``inputSchema``.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from chirp.tools.registry import ToolRegistry

OLLAMA_BASE = "http://localhost:11434"


def chirp_tools_to_ollama(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Convert chirp MCP tool schemas to Ollama function-calling format.

    MCP:    ``{name, description, inputSchema: {type, properties, required}}``
    Ollama: ``{type: "function", function: {name, description, parameters: ...}}``
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in registry.list_tools()
    ]


async def chat(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a non-streaming chat request to Ollama.

    Used for tool-calling rounds where we need the complete response
    (including ``tool_calls``) before dispatching.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    response = await client.post("/api/chat", json=payload)
    response.raise_for_status()
    return response.json()


async def chat_stream(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Stream a chat response from Ollama, yielding content tokens.

    Ollama streams newline-delimited JSON. Each chunk has a ``message``
    with partial ``content``. We yield each non-empty content fragment
    as it arrives.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    async with client.stream("POST", "/api/chat", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token

"""LLM provider implementations.

Each provider is a pair of functions: one for complete generation, one for
streaming. Both use raw HTTP via httpx — no provider SDKs required.

Supported providers:
    - ``anthropic`` — Claude models (Messages API)
    - ``openai`` — GPT models (Chat Completions API)
    - ``azure`` — Azure OpenAI deployments (OpenAI-compatible API)
    - ``gemini`` — Google Gemini (Generative Language API)
    - ``bedrock`` — AWS Bedrock Converse API (optional ``botocore`` for SigV4)
    - ``ollama`` — Local models via Ollama (OpenAI-compatible API)
    - ``lmstudio`` — Local models via LM Studio (OpenAI-compatible API)
    - ``localai`` — Local models via LocalAI (OpenAI-compatible API)

Provider string format: ``provider:model``
    - ``anthropic:claude-sonnet-4-20250514``
    - ``openai:gpt-4o``
    - ``azure:my-gpt4o-deployment`` (``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_API_KEY``)
    - ``gemini:gemini-2.0-flash`` (``GOOGLE_API_KEY`` or ``GEMINI_API_KEY``)
    - ``bedrock:anthropic.claude-3-sonnet-20240229-v1:0`` (AWS credentials + region)
    - ``ollama:llama3.2`` (uses ``OLLAMA_BASE`` env, default http://localhost:11434)
    - ``lmstudio:model-id`` (uses ``LMSTUDIO_BASE`` env, default http://localhost:1234)
    - ``localai:model-id`` (uses ``LOCALAI_BASE`` env, default http://localhost:8080)
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from chirp.ai._tool_calls import (
    ChatCompletion,
    parse_anthropic_completion,
    parse_openai_completion,
)
from chirp.ai.errors import ProviderError, ProviderNotInstalledError
from chirp.tools.registry import McpToolInfo

OPENAI_COMPAT_PROVIDERS = frozenset({"openai", "ollama", "lmstudio", "localai", "azure"})


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Parsed provider configuration."""

    provider: str
    model: str
    api_key: str
    base_url: str
    api_version: str = ""
    region: str = ""


def parse_provider(provider_string: str, /, *, api_key: str | None = None) -> ProviderConfig:
    """Parse a ``provider:model`` string into a config."""
    if ":" not in provider_string:
        msg = (
            f"Invalid provider string: {provider_string!r}. "
            "Expected format: 'provider:model' (e.g., 'anthropic:claude-sonnet-4-20250514')"
        )
        raise ValueError(msg)

    provider, model = provider_string.split(":", 1)
    provider = provider.lower().strip()
    model = model.strip()

    if provider == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return ProviderConfig(
            provider="anthropic",
            model=model,
            api_key=key,
            base_url="https://api.anthropic.com",
        )

    if provider == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        return ProviderConfig(
            provider="openai",
            model=model,
            api_key=key,
            base_url="https://api.openai.com",
        )

    if provider == "azure":
        key = api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        base = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        return ProviderConfig(
            provider="azure",
            model=model,
            api_key=key,
            base_url=base,
            api_version=version,
        )

    if provider == "gemini":
        key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
        return ProviderConfig(
            provider="gemini",
            model=model,
            api_key=key,
            base_url="https://generativelanguage.googleapis.com",
        )

    if provider == "bedrock":
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        return ProviderConfig(
            provider="bedrock",
            model=model,
            api_key="",
            base_url=f"https://bedrock-runtime.{region}.amazonaws.com",
            region=region,
        )

    if provider == "ollama":
        base = os.environ.get("OLLAMA_BASE", "http://localhost:11434").rstrip("/")
        return ProviderConfig(
            provider="ollama",
            model=model,
            api_key=api_key or "ollama",
            base_url=base,
        )

    if provider == "lmstudio":
        base = os.environ.get("LMSTUDIO_BASE", "http://localhost:1234").rstrip("/")
        return ProviderConfig(
            provider="lmstudio",
            model=model,
            api_key=api_key or "lmstudio",
            base_url=base,
        )

    if provider == "localai":
        base = os.environ.get("LOCALAI_BASE", "http://localhost:8080").rstrip("/")
        return ProviderConfig(
            provider="localai",
            model=model,
            api_key=api_key or "localai",
            base_url=base,
        )

    msg = (
        f"Unsupported provider: {provider!r}. Supported: anthropic, openai, azure, "
        "gemini, bedrock, ollama, lmstudio, localai"
    )
    raise ValueError(msg)


def _get_httpx() -> Any:
    """Import httpx or raise a clear error."""
    try:
        import httpx

        return httpx
    except ImportError:
        msg = "chirp.ai requires 'httpx' for LLM API calls. Install it with: pip install chirp[ai]"
        raise ProviderNotInstalledError(msg) from None


def _openai_chat_url(config: ProviderConfig) -> str:
    if config.provider == "azure":
        return (
            f"{config.base_url}/openai/deployments/{quote(config.model, safe='')}"
            f"/chat/completions?api-version={config.api_version}"
        )
    return f"{config.base_url}/v1/chat/completions"


def _openai_auth_headers(config: ProviderConfig) -> dict[str, str]:
    if config.provider == "azure":
        return {"api-key": config.api_key, "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}


def _native_json_schema_body(
    body: dict[str, Any],
    *,
    config: ProviderConfig,
    json_schema: dict[str, Any] | None,
) -> None:
    if json_schema is None:
        return
    if config.provider in ("openai", "azure"):
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": json_schema["name"],
                "strict": True,
                "schema": json_schema["schema"],
            },
        }


async def _iter_sse_events(response: Any) -> AsyncIterator[dict[str, Any]]:
    """Parse SSE events from response stream. Yields parsed JSON event dicts."""
    async for line in response.aiter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload.strip() == "[DONE]":
            break
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue


# =============================================================================
# Anthropic (Messages API)
# =============================================================================


async def anthropic_generate(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    json_schema: dict[str, Any] | None = None,
) -> str:
    """Generate a complete response from Anthropic's Messages API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    if json_schema is not None:
        body["output_format"] = {
            "type": "json_schema",
            "schema": json_schema["schema"],
        }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.base_url}/v1/messages",
            json=body,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    if response.status_code != 200:
        raise ProviderError("anthropic", response.status_code, response.text)

    data = response.json()
    return data["content"][0]["text"]


async def anthropic_complete(
    config: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> ChatCompletion:
    """Generate a completion, optionally with tool-use blocks."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.base_url}/v1/messages",
            json=body,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    if response.status_code != 200:
        raise ProviderError("anthropic", response.status_code, response.text)

    return parse_anthropic_completion(response.json())


async def anthropic_stream(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
) -> AsyncIterator[str]:
    """Stream text tokens from Anthropic's Messages API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    if system:
        body["system"] = system

    async with (
        httpx.AsyncClient() as client,
        client.stream(
            "POST",
            f"{config.base_url}/v1/messages",
            json=body,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        ) as response,
    ):
        if response.status_code != 200:
            text = await response.aread()
            raise ProviderError("anthropic", response.status_code, text.decode())

        async for event in _iter_sse_events(response):
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield text


# =============================================================================
# OpenAI-compatible (Chat Completions API)
# =============================================================================


async def openai_generate(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    json_schema: dict[str, Any] | None = None,
) -> str:
    """Generate a complete response from an OpenAI-compatible Chat Completions API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    _native_json_schema_body(body, config=config, json_schema=json_schema)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _openai_chat_url(config),
            json=body,
            headers=_openai_auth_headers(config),
            timeout=120.0,
        )

    if response.status_code != 200:
        raise ProviderError(config.provider, response.status_code, response.text)

    data = response.json()
    return data["choices"][0]["message"]["content"]


async def openai_complete(
    config: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    tools: list[dict[str, Any]] | None = None,
) -> ChatCompletion:
    """Generate a chat completion, optionally with function tools."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _openai_chat_url(config),
            json=body,
            headers=_openai_auth_headers(config),
            timeout=120.0,
        )

    if response.status_code != 200:
        raise ProviderError(config.provider, response.status_code, response.text)

    return parse_openai_completion(response.json())


async def openai_stream(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> AsyncIterator[str]:
    """Stream text tokens from an OpenAI-compatible Chat Completions API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    async with (
        httpx.AsyncClient() as client,
        client.stream(
            "POST",
            _openai_chat_url(config),
            json=body,
            headers=_openai_auth_headers(config),
            timeout=120.0,
        ) as response,
    ):
        if response.status_code != 200:
            text = await response.aread()
            raise ProviderError(config.provider, response.status_code, text.decode())

        async for event in _iter_sse_events(response):
            choices = event.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content


# =============================================================================
# Google Gemini
# =============================================================================


def _gemini_contents(
    messages: list[dict[str, str]],
    *,
    system: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    contents: list[dict[str, Any]] = []
    system_instruction: dict[str, Any] | None = None
    if system:
        system_instruction = {"parts": [{"text": system}]}
    for message in messages:
        role = "user" if message["role"] in ("user", "tool") else "model"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    return contents, system_instruction


async def gemini_generate(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    json_schema: dict[str, Any] | None = None,
) -> str:
    """Generate a complete response from Google Gemini."""
    httpx = _get_httpx()
    contents, system_instruction = _gemini_contents(messages, system=system)

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_instruction is not None:
        body["systemInstruction"] = system_instruction
    if json_schema is not None:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = json_schema["schema"]

    url = (
        f"{config.base_url}/v1beta/models/{quote(config.model, safe='')}:generateContent"
        f"?key={config.api_key}"
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=body, timeout=120.0)

    if response.status_code != 200:
        raise ProviderError("gemini", response.status_code, response.text)

    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def gemini_complete(
    config: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    tools: Sequence[McpToolInfo] | None = None,
) -> ChatCompletion:
    """Generate a Gemini completion with optional function declarations."""
    httpx = _get_httpx()
    str_messages = [{"role": m["role"], "content": str(m.get("content", ""))} for m in messages]
    contents, system_instruction = _gemini_contents(str_messages, system=system)

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_instruction is not None:
        body["systemInstruction"] = system_instruction
    if tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["inputSchema"],
                    }
                    for t in tools
                ]
            }
        ]

    url = (
        f"{config.base_url}/v1beta/models/{quote(config.model, safe='')}:generateContent"
        f"?key={config.api_key}"
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=body, timeout=120.0)

    if response.status_code != 200:
        raise ProviderError("gemini", response.status_code, response.text)

    data = response.json()
    candidate = data["candidates"][0]["content"]
    parts = candidate.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if "text" in p]
    function_calls = [
        {
            "call_id": p["functionCall"].get("name", "call"),
            "name": p["functionCall"]["name"],
            "arguments": p["functionCall"].get("args", {}),
        }
        for p in parts
        if "functionCall" in p
    ]
    content = "".join(text_parts)
    assistant_message = {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call["call_id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"]),
                },
            }
            for call in function_calls
        ]
        if function_calls
        else None,
    }
    return ChatCompletion(
        content=content,
        tool_calls=tuple(function_calls),
        assistant_message=assistant_message,
    )


async def gemini_stream(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
) -> AsyncIterator[str]:
    """Stream text tokens from Google Gemini."""
    httpx = _get_httpx()
    contents, system_instruction = _gemini_contents(messages, system=system)

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_instruction is not None:
        body["systemInstruction"] = system_instruction

    url = (
        f"{config.base_url}/v1beta/models/{quote(config.model, safe='')}:streamGenerateContent"
        f"?alt=sse&key={config.api_key}"
    )
    async with (
        httpx.AsyncClient() as client,
        client.stream("POST", url, json=body, timeout=120.0) as response,
    ):
        if response.status_code != 200:
            text = await response.aread()
            raise ProviderError("gemini", response.status_code, text.decode())

        async for event in _iter_sse_events(response):
            candidates = event.get("candidates", [])
            if not candidates:
                continue
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                text = part.get("text", "")
                if text:
                    yield text


# =============================================================================
# AWS Bedrock (Converse API)
# =============================================================================


def _bedrock_signed_headers(
    *,
    method: str,
    url: str,
    body: bytes,
    region: str,
) -> dict[str, str]:
    try:
        import botocore.session
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
    except ImportError as exc:
        msg = (
            "bedrock requires botocore for AWS SigV4 signing. "
            "Install it with: pip install chirp[ai-bedrock]"
        )
        raise ProviderNotInstalledError(msg) from exc

    session = botocore.session.get_session()
    credentials = session.get_credentials()
    if credentials is None:
        msg = "bedrock requires AWS credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)"
        raise ProviderNotInstalledError(msg)

    request = AWSRequest(
        method=method,
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "bedrock", region).add_auth(request)
    return dict(request.headers)


def _bedrock_messages(
    messages: list[dict[str, str]],
    *,
    system: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = "user" if message["role"] in ("user", "tool") else "assistant"
        converted.append({"role": role, "content": [{"text": message["content"]}]})
    system_blocks = [{"text": system}] if system else None
    return converted, system_blocks


def _bedrock_text_from_response(data: dict[str, Any]) -> str:
    message = data.get("output", {}).get("message", {})
    parts = message.get("content", [])
    return "".join(part.get("text", "") for part in parts if "text" in part)


async def bedrock_generate(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
) -> str:
    """Generate a complete response via AWS Bedrock Converse."""
    httpx = _get_httpx()
    converted, system_blocks = _bedrock_messages(messages, system=system)
    body = {
        "messages": converted,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system_blocks is not None:
        body["system"] = system_blocks

    payload = json.dumps(body).encode()
    url = f"{config.base_url}/model/{quote(config.model, safe='')}/converse"
    headers = _bedrock_signed_headers(
        method="POST",
        url=url,
        body=payload,
        region=config.region,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(url, content=payload, headers=headers, timeout=120.0)

    if response.status_code != 200:
        raise ProviderError("bedrock", response.status_code, response.text)

    return _bedrock_text_from_response(response.json())


async def bedrock_complete(
    config: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    tools: Sequence[McpToolInfo] | None = None,
) -> ChatCompletion:
    """Generate a Bedrock Converse completion with optional tool config."""
    httpx = _get_httpx()
    str_messages = [{"role": m["role"], "content": str(m.get("content", ""))} for m in messages]
    converted, system_blocks = _bedrock_messages(str_messages, system=system)
    body: dict[str, Any] = {
        "messages": converted,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system_blocks is not None:
        body["system"] = system_blocks
    if tools:
        body["toolConfig"] = {
            "tools": [
                {
                    "toolSpec": {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": {"json": t["inputSchema"]},
                    }
                }
                for t in tools
            ]
        }

    payload = json.dumps(body).encode()
    url = f"{config.base_url}/model/{quote(config.model, safe='')}/converse"
    headers = _bedrock_signed_headers(
        method="POST",
        url=url,
        body=payload,
        region=config.region,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(url, content=payload, headers=headers, timeout=120.0)

    if response.status_code != 200:
        raise ProviderError("bedrock", response.status_code, response.text)

    data = response.json()
    message = data.get("output", {}).get("message", {})
    parts = message.get("content", [])
    text = "".join(part.get("text", "") for part in parts if "text" in part)
    tool_calls = [
        {
            "call_id": part["toolUse"]["toolUseId"],
            "name": part["toolUse"]["name"],
            "arguments": part["toolUse"].get("input", {}),
        }
        for part in parts
        if "toolUse" in part
    ]
    assistant_message = {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call["call_id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"]),
                },
            }
            for call in tool_calls
        ]
        if tool_calls
        else None,
    }
    return ChatCompletion(
        content=text,
        tool_calls=tuple(tool_calls),
        assistant_message=assistant_message,
    )


async def bedrock_stream(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
) -> AsyncIterator[str]:
    """Stream text tokens via AWS Bedrock Converse Stream."""
    httpx = _get_httpx()
    converted, system_blocks = _bedrock_messages(messages, system=system)
    body: dict[str, Any] = {
        "messages": converted,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system_blocks is not None:
        body["system"] = system_blocks

    payload = json.dumps(body).encode()
    url = f"{config.base_url}/model/{quote(config.model, safe='')}/converse-stream"
    headers = _bedrock_signed_headers(
        method="POST",
        url=url,
        body=payload,
        region=config.region,
    )

    async with (
        httpx.AsyncClient() as client,
        client.stream("POST", url, content=payload, headers=headers, timeout=120.0) as response,
    ):
        if response.status_code != 200:
            text = await response.aread()
            raise ProviderError("bedrock", response.status_code, text.decode())

        async for event in _iter_sse_events(response):
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            text = delta.get("text", "")
            if text:
                yield text

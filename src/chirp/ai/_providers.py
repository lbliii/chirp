"""LLM provider implementations.

Each provider is a pair of functions: one for complete generation, one for
streaming. Both use raw HTTP via httpx — no provider SDKs required.

Supported providers:
    - ``anthropic`` — Claude models (Messages API)
    - ``openai`` — GPT models (Chat Completions API)
    - ``ollama`` — Local models via Ollama (OpenAI-compatible API)

Provider string format: ``provider:model``
    - ``anthropic:claude-sonnet-4-20250514``
    - ``openai:gpt-4o``
    - ``ollama:llama3.2`` (uses OLLAMA_BASE env, default http://localhost:11434)
"""

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from chirp.ai.errors import ProviderError, ProviderNotInstalledError


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Parsed provider configuration."""

    provider: str
    model: str
    api_key: str
    base_url: str


def parse_provider(provider_string: str, /, *, api_key: str | None = None) -> ProviderConfig:
    """Parse a ``provider:model`` string into a config.

    API keys are resolved in order:
        1. Explicit ``api_key`` parameter
        2. Environment variable (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``)
    """
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

    if provider == "ollama":
        base = os.environ.get("OLLAMA_BASE", "http://localhost:11434").rstrip("/")
        return ProviderConfig(
            provider="ollama",
            model=model,
            api_key=api_key or "ollama",  # Required by API but ignored
            base_url=base,
        )

    msg = f"Unsupported provider: {provider!r}. Supported: anthropic, openai, ollama"
    raise ValueError(msg)


def _get_httpx() -> Any:
    """Import httpx or raise a clear error."""
    try:
        import httpx

        return httpx
    except ImportError:
        msg = (
            "chirp.ai requires 'httpx' for LLM API calls. "
            "Install it with: pip install chirp[ai]"
        )
        raise ProviderNotInstalledError(msg) from None


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

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{config.base_url}/v1/messages",
            json=body,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        ) as response:
            if response.status_code != 200:
                text = await response.aread()
                raise ProviderError("anthropic", response.status_code, text.decode())

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text


# =============================================================================
# OpenAI (Chat Completions API)
# =============================================================================


async def openai_generate(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Generate a complete response from OpenAI's Chat Completions API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.base_url}/v1/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    if response.status_code != 200:
        raise ProviderError("openai", response.status_code, response.text)

    data = response.json()
    return data["choices"][0]["message"]["content"]


async def openai_stream(
    config: ProviderConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> AsyncIterator[str]:
    """Stream text tokens from OpenAI's Chat Completions API."""
    httpx = _get_httpx()

    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{config.base_url}/v1/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        ) as response:
            if response.status_code != 200:
                text = await response.aread()
                raise ProviderError("openai", response.status_code, text.decode())

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

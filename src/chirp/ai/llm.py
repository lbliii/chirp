"""LLM — Typed async LLM access.

Provider string in, typed results out. Streaming-native.

The ``LLM`` class wraps provider-specific HTTP calls behind a unified
interface. Both ``generate()`` and ``stream()`` support text and
structured (dataclass) output modes.

Free-threading safety:
    - LLM instances are effectively immutable after construction
    - httpx.AsyncClient is created per-request (no shared mutable state)
    - ProviderConfig is a frozen dataclass
"""

import dataclasses
from collections.abc import AsyncIterator
from typing import Any, overload

from chirp.ai._providers import (
    anthropic_generate,
    anthropic_stream,
    openai_generate,
    openai_stream,
    parse_provider,
)
from chirp.ai._structured import dataclass_to_schema, parse_structured
from chirp.ai.errors import AIError


class LLM:
    """Typed async LLM access.

    Usage::

        llm = LLM("anthropic:claude-sonnet-4-20250514")

        # Text generation
        text = await llm.generate("Explain quantum computing")

        # Text streaming
        async for token in llm.stream("Analyze this:"):
            print(token, end="")

        # Structured output (frozen dataclass)
        @dataclass(frozen=True, slots=True)
        class Summary:
            title: str
            key_points: list[str]
            sentiment: str

        summary = await llm.generate(Summary, prompt="Summarize: ...")

    Provider string format: ``provider:model``

        - ``anthropic:claude-sonnet-4-20250514``
        - ``openai:gpt-4o``
    """

    __slots__ = ("_config", "_default_max_tokens", "_default_temperature")

    def __init__(
        self,
        provider: str,
        /,
        *,
        api_key: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> None:
        self._config = parse_provider(provider, api_key=api_key)
        self._default_max_tokens = max_tokens
        self._default_temperature = temperature

    @property
    def provider(self) -> str:
        """The provider name (e.g., 'anthropic', 'openai')."""
        return self._config.provider

    @property
    def model(self) -> str:
        """The model name (e.g., 'claude-sonnet-4-20250514')."""
        return self._config.model

    # -- Generate (complete response) --

    @overload
    async def generate(self, prompt: str, /, **kwargs: Any) -> str: ...
    @overload
    async def generate[T](self, cls: type[T], /, *, prompt: str, **kwargs: Any) -> T: ...

    async def generate(
        self,
        prompt_or_cls: str | type,
        /,
        *,
        prompt: str | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        """Generate a complete LLM response.

        **Text mode** — pass a prompt string, get a string back::

            text = await llm.generate("Explain quantum computing")

        **Structured mode** — pass a dataclass type + prompt, get a typed
        instance back::

            summary = await llm.generate(Summary, prompt="Summarize: ...")

        The LLM is instructed to return JSON matching the dataclass schema.
        The response is parsed and mapped to a frozen dataclass instance.
        """
        max_t = max_tokens or self._default_max_tokens
        temp = temperature if temperature is not None else self._default_temperature

        if isinstance(prompt_or_cls, str):
            # Text mode
            messages = [{"role": "user", "content": prompt_or_cls}]
            return await self._generate_raw(
                messages, system=system, max_tokens=max_t, temperature=temp
            )

        # Structured mode
        cls = prompt_or_cls
        if prompt is None:
            msg = "Structured generation requires a 'prompt' keyword argument"
            raise AIError(msg)

        if not dataclasses.is_dataclass(cls):
            msg = (
                f"{cls.__name__} is not a dataclass — structured output requires frozen dataclasses"
            )
            raise TypeError(msg)

        schema = dataclass_to_schema(cls)
        structured_prompt = (
            f"{prompt}\n\n"
            f"Respond with a JSON object matching this schema:\n"
            f"```json\n{schema}\n```\n"
            f"Return ONLY the JSON object, no other text."
        )
        messages = [{"role": "user", "content": structured_prompt}]
        text = await self._generate_raw(messages, system=system, max_tokens=max_t, temperature=temp)
        return parse_structured(cls, text)

    # -- Stream (incremental response) --

    @overload
    def stream(self, prompt: str, /, **kwargs: Any) -> AsyncIterator[str]: ...
    @overload
    def stream[T](self, cls: type[T], /, *, prompt: str, **kwargs: Any) -> AsyncIterator[str]: ...

    async def stream(  # type: ignore[misc]
        self,
        prompt_or_cls: str | type,
        /,
        *,
        prompt: str | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream LLM response tokens incrementally.

        **Text mode** — yields string tokens::

            async for token in llm.stream("Analyze this:"):
                print(token, end="")

        **Structured mode** — streams tokens (for display) while building
        toward a structured result. Caller accumulates tokens for parsing.

        Both modes yield ``str`` tokens. For structured output, accumulate
        the full text and parse with ``parse_structured()`` after streaming
        completes.
        """
        max_t = max_tokens or self._default_max_tokens
        temp = temperature if temperature is not None else self._default_temperature

        if isinstance(prompt_or_cls, str):
            messages = [{"role": "user", "content": prompt_or_cls}]
        else:
            if prompt is None:
                msg = "Structured streaming requires a 'prompt' keyword argument"
                raise AIError(msg)
            messages = [{"role": "user", "content": prompt}]

        async for token in self._stream_raw(
            messages, system=system, max_tokens=max_t, temperature=temp
        ):
            yield token

    # -- Internal dispatch --

    async def _generate_raw(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Dispatch to provider-specific generation."""
        if self._config.provider == "anthropic":
            return await anthropic_generate(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
            )
        if self._config.provider in ("openai", "ollama"):
            # OpenAI and Ollama use system message in messages array
            if system:
                messages = [{"role": "system", "content": system}, *messages]
            return await openai_generate(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        msg = f"Unsupported provider: {self._config.provider}"
        raise AIError(msg)

    async def _stream_raw(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        """Dispatch to provider-specific streaming."""
        if self._config.provider == "anthropic":
            async for token in anthropic_stream(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
            ):
                yield token
            return

        if self._config.provider in ("openai", "ollama"):
            if system:
                messages = [{"role": "system", "content": system}, *messages]
            async for token in openai_stream(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield token
            return

        msg = f"Unsupported provider: {self._config.provider}"
        raise AIError(msg)

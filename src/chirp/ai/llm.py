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

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, overload

from chirp.ai._providers import (
    OPENAI_COMPAT_PROVIDERS,
    anthropic_complete,
    anthropic_generate,
    anthropic_stream,
    bedrock_complete,
    bedrock_generate,
    bedrock_stream,
    gemini_complete,
    gemini_generate,
    gemini_stream,
    openai_complete,
    openai_generate,
    openai_stream,
    parse_provider,
)
from chirp.ai._structured import (
    is_structured_type,
    parse_structured,
    schema_for_type,
    structured_repair_prompt,
)
from chirp.ai._tool_calls import (
    ChatCompletion,
    tools_from_registry,
    tools_to_anthropic,
    tools_to_openai,
)
from chirp.ai.errors import AIError, StructuredOutputError
from chirp.ai.events import DoneEvent, ErrorEvent, StreamEvent, TokenEvent
from chirp.telemetry import _SpanScope, trace_span

if TYPE_CHECKING:
    from chirp.tools.registry import ToolRegistry

_OPENAI_COMPAT_PROVIDERS = OPENAI_COMPAT_PROVIDERS


class LLM:
    """Typed async LLM access.

    Usage::

        llm = LLM("anthropic:claude-sonnet-4-20250514")

        # Text generation
        text = await llm.generate("Explain quantum computing")

        # Text streaming
        async for token in llm.stream("Analyze this:"):
            print(token, end="")

        # Structured output (frozen dataclass or Pydantic model)
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
        structured_retries: int = 2,
    ) -> Any:
        """Generate a complete LLM response.

        **Text mode** — pass a prompt string, get a string back::

            text = await llm.generate("Explain quantum computing")

        **Structured mode** — pass a dataclass or Pydantic model type + prompt,
        get a typed instance back::

            summary = await llm.generate(Summary, prompt="Summarize: ...")

        The LLM is instructed to return JSON matching the dataclass schema.
        The response is parsed and mapped to a frozen dataclass instance.
        """
        max_t = max_tokens or self._default_max_tokens
        temp = temperature if temperature is not None else self._default_temperature

        if isinstance(prompt_or_cls, str):
            # Text mode
            messages = [{"role": "user", "content": prompt_or_cls}]
            with trace_span(
                "llm.generate",
                provider=self._config.provider,
                model=self._config.model,
            ):
                return await self._generate_raw(
                    messages, system=system, max_tokens=max_t, temperature=temp
                )

        # Structured mode
        cls = prompt_or_cls
        if prompt is None:
            msg = "Structured generation requires a 'prompt' keyword argument"
            raise AIError(msg)

        if not is_structured_type(cls):
            msg = (
                f"{getattr(cls, '__name__', cls)!r} is not a dataclass or Pydantic model — "
                "structured output requires frozen dataclasses or pydantic.BaseModel subclasses"
            )
            raise TypeError(msg)

        schema = schema_for_type(cls)
        structured_prompt = (
            f"{prompt}\n\n"
            f"Respond with a JSON object matching this schema:\n"
            f"```json\n{schema}\n```\n"
            f"Return ONLY the JSON object, no other text."
        )
        messages: list[dict[str, str]] = [{"role": "user", "content": structured_prompt}]
        schema_name = getattr(cls, "__name__", "response")
        with trace_span(
            "llm.generate",
            provider=self._config.provider,
            model=self._config.model,
            mode="structured",
        ):
            last_error: StructuredOutputError | None = None
            for attempt in range(structured_retries + 1):
                text = await self._generate_raw(
                    messages,
                    system=system,
                    max_tokens=max_t,
                    temperature=temp,
                    json_schema={"name": schema_name, "schema": schema},
                )
                try:
                    return parse_structured(cls, text)
                except StructuredOutputError as exc:
                    last_error = exc
                    if attempt >= structured_retries:
                        raise
                    messages = [
                        *messages,
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": structured_repair_prompt(error=exc, bad_text=text),
                        },
                    ]
            if last_error is not None:
                raise last_error
            msg = "Structured generation failed without a parse error"
            raise StructuredOutputError(msg)

    # -- Stream (incremental response) --

    @overload
    def stream(self, prompt: str, /, **kwargs: Any) -> AsyncIterator[str]: ...
    @overload
    def stream[T](self, cls: type[T], /, *, prompt: str, **kwargs: Any) -> AsyncIterator[str]: ...

    async def stream(
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

        scope = _SpanScope.start(
            "llm.stream",
            provider=self._config.provider,
            model=self._config.model,
        )
        token_count = 0
        try:
            async for token in self._stream_raw(
                messages, system=system, max_tokens=max_t, temperature=temp
            ):
                token_count += 1
                yield token
        except BaseException as exc:
            if scope is not None:
                scope.close(error=exc, tokens_out=token_count or None)
            raise
        else:
            if scope is not None:
                scope.close(tokens_out=token_count or None)

    # -- Complete (tool-aware, non-streaming) --

    async def complete(
        self,
        messages: list[dict[str, Any]],
        /,
        *,
        tools: ToolRegistry | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletion:
        """Generate a full model response, including tool-call requests."""
        max_t = max_tokens or self._default_max_tokens
        temp = temperature if temperature is not None else self._default_temperature
        tool_list = tools_from_registry(tools)

        with trace_span(
            "llm.generate",
            provider=self._config.provider,
            model=self._config.model,
            mode="tools" if tool_list else "text",
        ):
            if self._config.provider == "anthropic":
                anthropic_tools = tools_to_anthropic(tool_list) if tool_list else None
                return await anthropic_complete(
                    self._config,
                    messages,
                    max_tokens=max_t,
                    temperature=temp,
                    system=system,
                    tools=anthropic_tools,
                )
            if self._config.provider in _OPENAI_COMPAT_PROVIDERS:
                msgs = list(messages)
                if system:
                    msgs = [{"role": "system", "content": system}, *msgs]
                openai_tools = tools_to_openai(tool_list) if tool_list else None
                return await openai_complete(
                    self._config,
                    msgs,
                    max_tokens=max_t,
                    temperature=temp,
                    tools=openai_tools,
                )
            if self._config.provider == "gemini":
                return await gemini_complete(
                    self._config,
                    messages,
                    max_tokens=max_t,
                    temperature=temp,
                    system=system,
                    tools=tool_list,
                )
            if self._config.provider == "bedrock":
                return await bedrock_complete(
                    self._config,
                    messages,
                    max_tokens=max_t,
                    temperature=temp,
                    system=system,
                    tools=tool_list,
                )
        msg = f"Unsupported provider: {self._config.provider}"
        raise AIError(msg)

    # -- Stream events (unified event union) --

    async def stream_events(
        self,
        prompt_or_messages: str | list[dict[str, Any]],
        /,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield :class:`~chirp.ai.events.StreamEvent` tokens and lifecycle events."""
        max_t = max_tokens or self._default_max_tokens
        temp = temperature if temperature is not None else self._default_temperature

        if isinstance(prompt_or_messages, str):
            messages: list[dict[str, Any]] = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = list(prompt_or_messages)

        scope = _SpanScope.start(
            "llm.stream",
            provider=self._config.provider,
            model=self._config.model,
        )
        token_count = 0
        try:
            async for token in self._stream_raw(
                messages, system=system, max_tokens=max_t, temperature=temp
            ):
                token_count += 1
                yield TokenEvent(text=token)
            yield DoneEvent(tokens_out=token_count or None)
        except AIError as exc:
            yield ErrorEvent(error=exc)
            if scope is not None:
                scope.close(error=exc, tokens_out=token_count or None)
            raise
        except BaseException as exc:
            if scope is not None:
                scope.close(error=exc, tokens_out=token_count or None)
            raise
        else:
            if scope is not None:
                scope.close(tokens_out=token_count or None)

    # -- Internal dispatch --

    async def _generate_raw(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None,
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Dispatch to provider-specific generation."""
        if self._config.provider == "anthropic":
            return await anthropic_generate(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                json_schema=json_schema,
            )
        if self._config.provider in _OPENAI_COMPAT_PROVIDERS:
            msgs = list(messages)
            if system:
                msgs = [{"role": "system", "content": system}, *msgs]
            return await openai_generate(
                self._config,
                msgs,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=json_schema,
            )
        if self._config.provider == "gemini":
            return await gemini_generate(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                json_schema=json_schema,
            )
        if self._config.provider == "bedrock":
            return await bedrock_generate(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
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

        if self._config.provider in _OPENAI_COMPAT_PROVIDERS:
            msgs = list(messages)
            if system:
                msgs = [{"role": "system", "content": system}, *msgs]
            async for token in openai_stream(
                self._config,
                msgs,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield token
            return

        if self._config.provider == "gemini":
            async for token in gemini_stream(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
            ):
                yield token
            return

        if self._config.provider == "bedrock":
            async for token in bedrock_stream(
                self._config,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
            ):
                yield token
            return

        msg = f"Unsupported provider: {self._config.provider}"
        raise AIError(msg)

"""Core unit tests for chirp.ai — provider parsing, generate, stream, structured."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.ai._providers import parse_provider
from chirp.ai._structured import parse_structured
from chirp.ai.errors import AIError, ProviderError, StructuredOutputError
from chirp.ai.llm import LLM


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., Any],
) -> None:
    """Patch httpx.AsyncClient so all chirp.ai provider calls use *handler*."""
    import httpx

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


def _anthropic_generate_response(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _openai_generate_response(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": text}}]}


def _anthropic_stream_body(tokens: list[str]) -> bytes:
    lines: list[str] = []
    for token in tokens:
        payload = json.dumps(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": token},
            }
        )
        lines.append(f"data: {payload}")
    lines.append("data: [DONE]")
    return "\n".join(lines).encode()


def _openai_stream_body(tokens: list[str]) -> bytes:
    lines: list[str] = []
    for token in tokens:
        payload = json.dumps({"choices": [{"delta": {"content": token}}]})
        lines.append(f"data: {payload}")
    lines.append("data: [DONE]")
    return "\n".join(lines).encode()


class TestProviderParsing:
    """parse_provider() and LLM() constructor parsing."""

    def test_anthropic_provider(self) -> None:
        config = parse_provider("anthropic:claude-sonnet-4-20250514", api_key="sk-test")
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.api_key == "sk-test"
        assert config.base_url == "https://api.anthropic.com"

    def test_openai_provider(self) -> None:
        config = parse_provider("openai:gpt-4o", api_key="sk-openai")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.api_key == "sk-openai"

    def test_ollama_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_BASE", "http://ollama.test:11434")
        config = parse_provider("ollama:llama3.2")
        assert config.provider == "ollama"
        assert config.model == "llama3.2"
        assert config.base_url == "http://ollama.test:11434"

    def test_invalid_provider_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid provider string"):
            parse_provider("no-colon-model")

    def test_unsupported_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported provider"):
            parse_provider("not-a-provider:model")

    def test_llm_exposes_provider_and_model(self) -> None:
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        assert llm.provider == "openai"
        assert llm.model == "gpt-4o"


class TestLLMGenerate:
    """LLM.generate() text mode with mocked httpx."""

    @pytest.mark.asyncio
    async def test_anthropic_generate_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/messages"
            body = json.loads(request.content)
            assert body["model"] == "claude-sonnet-4-20250514"
            assert body["messages"] == [{"role": "user", "content": "Hello"}]
            return httpx.Response(200, json=_anthropic_generate_response("Hi there"))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("anthropic:claude-sonnet-4-20250514", api_key="sk-test")
        text = await llm.generate("Hello")
        assert text == "Hi there"

    @pytest.mark.asyncio
    async def test_openai_generate_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            body = json.loads(request.content)
            assert body["model"] == "gpt-4o"
            return httpx.Response(200, json=_openai_generate_response("OpenAI says hi"))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        text = await llm.generate("Hello")
        assert text == "OpenAI says hi"

    @pytest.mark.asyncio
    async def test_openai_generate_injects_system_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["messages"][0] == {"role": "system", "content": "Be brief."}
            return httpx.Response(200, json=_openai_generate_response("ok"))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        text = await llm.generate("Hello", system="Be brief.")
        assert text == "ok"

    @pytest.mark.asyncio
    async def test_provider_error_on_http_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="invalid key")

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="bad")
        with pytest.raises(ProviderError) as exc:
            await llm.generate("Hello")
        assert exc.value.provider == "openai"
        assert exc.value.status == 401


class TestLLMStream:
    """LLM.stream() token iteration with mocked httpx."""

    @pytest.mark.asyncio
    async def test_anthropic_stream_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/messages"
            body = json.loads(request.content)
            assert body["stream"] is True
            return httpx.Response(200, content=_anthropic_stream_body(["Hel", "lo"]))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("anthropic:claude-sonnet-4-20250514", api_key="sk-test")
        tokens = [token async for token in llm.stream("Hi")]
        assert tokens == ["Hel", "lo"]

    @pytest.mark.asyncio
    async def test_openai_stream_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            body = json.loads(request.content)
            assert body["stream"] is True
            return httpx.Response(200, content=_openai_stream_body(["A", "B", "C"]))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        tokens = [token async for token in llm.stream("Hi")]
        assert tokens == ["A", "B", "C"]


@dataclasses.dataclass(frozen=True, slots=True)
class _Summary:
    title: str
    key_points: list[str]


class TestStructuredOutput:
    """Structured dataclass generation and parsing."""

    @pytest.mark.asyncio
    async def test_generate_structured_dataclass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        payload = {"title": "Test", "key_points": ["a", "b"]}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openai_generate_response(json.dumps(payload)))

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        summary = await llm.generate(_Summary, prompt="Summarize this")
        assert summary == _Summary(title="Test", key_points=["a", "b"])

    def test_parse_structured_from_json_fence(self) -> None:
        text = 'Here is the result:\n```json\n{"title": "X", "key_points": ["y"]}\n```'
        summary = parse_structured(_Summary, text)
        assert summary.title == "X"
        assert summary.key_points == ["y"]

    def test_parse_structured_invalid_json_raises(self) -> None:
        with pytest.raises(StructuredOutputError, match="No JSON found"):
            parse_structured(_Summary, "not json at all")

    def test_parse_structured_malformed_json_raises(self) -> None:
        with pytest.raises(StructuredOutputError, match="Failed to parse"):
            parse_structured(_Summary, "{not valid json")

    @pytest.mark.asyncio
    async def test_structured_requires_prompt_kwarg(self) -> None:
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        with pytest.raises(AIError, match="prompt"):
            await llm.generate(_Summary)  # type: ignore[call-overload]

    @pytest.mark.asyncio
    async def test_structured_requires_dataclass_type(self) -> None:
        llm = LLM("openai:gpt-4o", api_key="sk-test")

        class NotADataclass:
            pass

        with pytest.raises(TypeError, match="dataclass or Pydantic"):
            await llm.generate(NotADataclass, prompt="nope")  # type: ignore[type-var]


@pytest.mark.issue(426)
class TestLLMAcceptance:
    """Acceptance gate for #426 — core LLM paths without live API keys."""

    @pytest.mark.asyncio
    async def test_both_provider_paths_exercised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        seen: set[str] = set()

        def handler(request: httpx.Request) -> httpx.Response:
            if "/v1/messages" in request.url.path:
                seen.add("anthropic")
                return httpx.Response(200, json=_anthropic_generate_response("anthropic ok"))
            seen.add("openai")
            return httpx.Response(200, json=_openai_generate_response("openai ok"))

        _install_mock_transport(monkeypatch, handler)

        anthropic = LLM("anthropic:claude-sonnet-4-20250514", api_key="sk-a")
        openai = LLM("openai:gpt-4o", api_key="sk-o")
        assert await anthropic.generate("x") == "anthropic ok"
        assert await openai.generate("x") == "openai ok"
        assert seen == {"anthropic", "openai"}

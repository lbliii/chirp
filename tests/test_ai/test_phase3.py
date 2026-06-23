"""Tests for Phase 3 AI hardening — structured output, providers, eval helpers."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.ai._providers import parse_provider
from chirp.ai._structured import parse_structured, schema_for_type
from chirp.ai.errors import StructuredOutputError
from chirp.ai.llm import LLM
from chirp.testing.eval import (
    LLMScript,
    collect_sse_message_text,
    install_llm_script,
    openai_completion,
)


def _install_mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    from chirp.testing.eval import install_mock_transport

    install_mock_transport(monkeypatch, handler)


@dataclasses.dataclass(frozen=True, slots=True)
class _Summary:
    title: str
    key_points: list[str]


@pytest.mark.issue(436)
class TestStructuredOutputHardening:
    @pytest.mark.asyncio
    async def test_retry_recovers_from_malformed_first_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        calls = {"n": 0}
        good = json.dumps({"title": "Fixed", "key_points": ["a"]})

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            text = "not json" if calls["n"] == 1 else good
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": text}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        summary = await llm.generate(_Summary, prompt="Summarize", structured_retries=1)
        assert summary == _Summary(title="Fixed", key_points=["a"])
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_openai_native_json_schema_requested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            payload = {"title": "Native", "key_points": ["x"]}
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(payload)}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        summary = await llm.generate(_Summary, prompt="Summarize")
        assert summary.title == "Native"
        body = seen["body"]
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["name"] == "_Summary"

    def test_pydantic_model_parse(self) -> None:
        pydantic = pytest.importorskip("pydantic")

        class Item(pydantic.BaseModel):
            title: str
            count: int

        schema = schema_for_type(Item)
        assert schema["properties"]["title"]["type"] == "string"
        parsed = parse_structured(Item, '{"title": "Hello", "count": 3}')
        assert parsed.title == "Hello"
        assert parsed.count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raise_structured_output_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "still not json"}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        with pytest.raises(StructuredOutputError):
            await llm.generate(_Summary, prompt="Summarize", structured_retries=0)


@pytest.mark.issue(444)
class TestAdditionalProviders:
    def test_gemini_provider_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        config = parse_provider("gemini:gemini-2.0-flash")
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"
        assert config.api_key == "gem-key"

    def test_azure_provider_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        config = parse_provider("azure:gpt-4o")
        assert config.provider == "azure"
        assert config.base_url == "https://my.openai.azure.com"
        assert config.api_version == "2024-10-21"

    def test_bedrock_provider_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        config = parse_provider("bedrock:anthropic.claude-3-haiku-20240307-v1:0")
        assert config.provider == "bedrock"
        assert config.region == "us-west-2"
        assert "us-west-2" in config.base_url

    @pytest.mark.asyncio
    async def test_gemini_generate_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert ":generateContent" in request.url.path
            assert "key=gem-key" in str(request.url)
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "Gemini says hi"}]}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("gemini:gemini-2.0-flash", api_key="gem-key")
        text = await llm.generate("Hello")
        assert text == "Gemini says hi"

    @pytest.mark.asyncio
    async def test_azure_generate_uses_deployment_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["api_key"] = request.headers.get("api-key", "")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Azure ok"}}]},
            )

        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my.openai.azure.com")
        _install_mock_transport(monkeypatch, handler)
        llm = LLM("azure:my-deployment", api_key="azure-key")
        text = await llm.generate("Hello")
        assert text == "Azure ok"
        assert "/openai/deployments/my-deployment/chat/completions" in seen["path"]
        assert seen["api_key"] == "azure-key"

    @pytest.mark.asyncio
    async def test_bedrock_generate_requires_botocore(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("botocore")
        import botocore.session
        import httpx

        class _Creds:
            access_key = "AKIATEST"
            secret_key = "secret"
            token = None

            def get_frozen_credentials(self):
                return self

        session = botocore.session.get_session()
        monkeypatch.setattr(session, "get_credentials", lambda: _Creds())
        monkeypatch.setattr("botocore.session.get_session", lambda: session)

        def handler(request: httpx.Request) -> httpx.Response:
            assert "/converse" in request.url.path
            assert request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256")
            return httpx.Response(
                200,
                json={"output": {"message": {"content": [{"text": "Bedrock ok"}]}}},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("bedrock:anthropic.claude-3-haiku-20240307-v1:0")
        text = await llm.generate("Hello")
        assert text == "Bedrock ok"


@pytest.mark.issue(443)
class TestEvalHelpers:
    @pytest.mark.asyncio
    async def test_install_llm_script_tracks_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        script = LLMScript(
            completes=[openai_completion("first"), openai_completion("second")],
            stream_tokens=["tok"],
        )
        tracker = install_llm_script(monkeypatch, script)

        async with httpx.AsyncClient() as client:
            r1 = await client.post(
                "http://test/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            assert r1.json()["choices"][0]["message"]["content"] == "first"
            r2 = await client.post(
                "http://test/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "again"}]},
            )
            assert r2.json()["choices"][0]["message"]["content"] == "second"
            rs = await client.post(
                "http://test/v1/chat/completions",
                json={"messages": [], "stream": True},
            )
            assert rs.status_code == 200

        assert tracker.complete_calls == 2
        assert tracker.stream_calls == 1
        assert len(tracker.captured_messages) == 2

    def test_collect_sse_message_text(self) -> None:
        from chirp.realtime.events import SSEEvent
        from chirp.testing.sse import SSETestResult

        result = SSETestResult(
            events=(
                SSEEvent(event="message", data="Hello "),
                SSEEvent(event="message", data="world"),
                SSEEvent(event="done", data=""),
            ),
            heartbeats=0,
            status=200,
        )
        assert collect_sse_message_text(result) == "Hello world"

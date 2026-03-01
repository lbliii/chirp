"""Tests for the llm_playground example — side-by-side LLM comparison.

All Ollama HTTP calls are replaced with in-process fakes so no running
Ollama instance is needed.
"""

from chirp.testing import TestClient, assert_is_fragment

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}
_FAKE_MODELS = ["llama3.2", "mistral:latest"]


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


async def _fake_ollama_models():
    """Return a canned model list without hitting the network."""
    return _FAKE_MODELS


class _FakeLLM:
    """Drop-in replacement for chirp.ai.LLM that yields preset tokens."""

    def __init__(self, *args, **kwargs):
        pass

    async def stream(self, prompt, /, **kwargs):
        for token in ["Hello", " ", "world"]:
            yield token


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------


class TestIndexPage:
    """GET / renders the model-selection UI."""

    async def test_renders_ok(self, example_module, monkeypatch) -> None:
        monkeypatch.setattr(example_module, "_ollama_models", _fake_ollama_models)
        async with TestClient(example_module.app) as client:
            response = await client.get("/")
        assert response.status == 200

    async def test_lists_available_models(self, example_module, monkeypatch) -> None:
        monkeypatch.setattr(example_module, "_ollama_models", _fake_ollama_models)
        async with TestClient(example_module.app) as client:
            response = await client.get("/")
        assert "llama3.2" in response.text
        assert "mistral:latest" in response.text

    async def test_no_models_still_renders(self, example_module, monkeypatch) -> None:
        """Page renders gracefully when Ollama returns an empty list."""

        async def _no_models():
            return []

        monkeypatch.setattr(example_module, "_ollama_models", _no_models)
        async with TestClient(example_module.app) as client:
            response = await client.get("/")
        assert response.status == 200


# ---------------------------------------------------------------------------
# /ask — returns scaffolding with stream URLs
# ---------------------------------------------------------------------------


class TestAskEndpoint:
    """POST /ask — returns a Fragment with stream_url(s) for the SSE panel."""

    async def test_empty_prompt_returns_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                body=b"prompt=",
                headers=_FORM_CT,
            )
        # Empty prompt → "empty" fragment (still a 200, not an error)
        assert response.status == 200

    async def test_valid_prompt_returns_compare_fragment(self, example_module, monkeypatch) -> None:
        monkeypatch.setattr(example_module, "_ollama_models", _fake_ollama_models)
        async with TestClient(example_module.app) as client:
            response = await client.post(
                "/ask",
                body=b"prompt=What+is+chirp%3F&model_a=llama3.2&model_b=mistral%3Alatest",
                headers=_FORM_CT,
            )
        assert response.status == 200
        assert_is_fragment(response)
        # Both stream URLs should be embedded so htmx opens the SSE connections
        assert "/ask/stream" in response.text

    async def test_single_model_prompt(self, example_module, monkeypatch) -> None:
        """When both models are the same the fragment still renders."""
        monkeypatch.setattr(example_module, "_ollama_models", _fake_ollama_models)
        async with TestClient(example_module.app) as client:
            response = await client.post(
                "/ask",
                body=b"prompt=Hello&model_a=llama3.2&model_b=llama3.2",
                headers=_FORM_CT,
            )
        assert response.status == 200
        assert_is_fragment(response)


# ---------------------------------------------------------------------------
# /ask/stream — SSE token delivery
# ---------------------------------------------------------------------------


class TestAskStream:
    """GET /ask/stream — streams LLM tokens as SSE fragment events."""

    async def test_stream_connects(self, example_module, monkeypatch) -> None:
        """SSE endpoint returns event-stream content type."""
        monkeypatch.setattr(example_module, "LLM", _FakeLLM)
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?prompt=Hello&model=llama3.2",
                max_events=5,
                timeout=3.0,
            )
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"

    async def test_stream_emits_done_event(self, example_module, monkeypatch) -> None:
        """Generator yields a ``done`` sentinel after all tokens."""
        monkeypatch.setattr(example_module, "LLM", _FakeLLM)
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?prompt=Hello&model=llama3.2",
                max_events=10,
                timeout=3.0,
            )
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) >= 1

    async def test_stream_empty_prompt(self, example_module, monkeypatch) -> None:
        """Empty prompt returns a fragment and done without calling the LLM."""
        monkeypatch.setattr(example_module, "LLM", _FakeLLM)
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?prompt=&model=llama3.2",
                max_events=5,
                timeout=2.0,
            )
        assert result.status == 200
        # Should get a "done" event even for empty prompts
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) >= 1

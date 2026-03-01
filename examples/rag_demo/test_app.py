"""Tests for the rag_demo example — RAG-powered docs with streaming AI answers.

External dependencies (Ollama, remote doc sync) are replaced with
in-process fakes.  The database is a per-test temp SQLite file.
"""

from types import SimpleNamespace

from chirp.testing import TestClient, assert_is_fragment

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Minimal LLM stand-in that yields preset tokens without HTTP calls."""

    def __init__(self, *args, **kwargs):
        self.model = "fake:model"

    async def stream(self, prompt, /, **kwargs):
        for token in ["This", " is", " a", " test", " answer."]:
            yield token


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------


class TestIndexPage:
    """GET / renders the docs homepage."""

    async def test_renders_ok(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
        assert response.status == 200

    async def test_contains_search_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
        assert response.status == 200
        assert "question" in response.text.lower()


# ---------------------------------------------------------------------------
# /ask — returns Fragment with source list and stream URL
# ---------------------------------------------------------------------------


class TestAskEndpoint:
    """POST /ask — retrieves docs and returns scaffolding for SSE streaming."""

    async def test_empty_question_returns_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                body=b"question=",
                headers=_FORM_CT,
            )
        assert response.status == 200
        assert_is_fragment(response)

    async def test_valid_question_returns_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                body=b"question=What+is+chirp%3F",
                headers=_FORM_CT,
            )
        assert response.status == 200
        assert_is_fragment(response)
        # Fragment must embed the stream URL for htmx to open SSE
        assert "/ask/stream" in response.text

    async def test_multiline_batch_question(self, example_app) -> None:
        """Multiple lines → batch result fragment."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                body=b"question=What+is+chirp%3F%0AWhat+is+kida%3F",
                headers=_FORM_CT,
            )
        assert response.status == 200
        assert_is_fragment(response)


# ---------------------------------------------------------------------------
# /ask/stream — SSE token delivery
# ---------------------------------------------------------------------------


class TestAskStream:
    """GET /ask/stream — streams AI tokens as SSE fragment events."""

    async def test_stream_connects(self, example_module, monkeypatch) -> None:
        """SSE endpoint returns text/event-stream content type."""
        monkeypatch.setattr(example_module, "llm", _FakeLLM())
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?question=What+is+chirp",
                max_events=10,
                timeout=3.0,
            )
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"

    async def test_stream_emits_done_event(self, example_module, monkeypatch) -> None:
        """Generator emits a ``done`` sentinel after all tokens."""
        monkeypatch.setattr(example_module, "llm", _FakeLLM())
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?question=What+is+chirp",
                max_events=15,
                timeout=3.0,
            )
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) >= 1

    async def test_stream_empty_question(self, example_module, monkeypatch) -> None:
        """Empty question returns a fragment and done without calling the LLM."""
        monkeypatch.setattr(example_module, "llm", _FakeLLM())
        async with TestClient(example_module.app) as client:
            result = await client.sse(
                "/ask/stream?question=",
                max_events=5,
                timeout=2.0,
            )
        assert result.status == 200
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) >= 1


# ---------------------------------------------------------------------------
# /share/{slug} — read-only shared Q&A
# ---------------------------------------------------------------------------


class TestShareEndpoint:
    """GET /share/{slug} — renders a shared Q&A by slug."""

    async def test_missing_slug_returns_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/share/does-not-exist")
        assert response.status == 200
        assert "not found" in response.text.lower()

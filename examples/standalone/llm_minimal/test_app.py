"""Tests for llm_minimal — simulated streaming, no Ollama or API keys.

Covers both streaming paths the README compares:
- ``/ask``    — TemplateStream (chunked HTML body)
- ``/stream`` — EventStream (one SSE Fragment per token)
"""

from chirp.testing import TestClient, assert_sse_wired


class TestIndex:
    """The form page renders and wires up both streaming paths."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_has_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'action="/ask"' in response.text
            assert 'name="prompt"' in response.text

    async def test_index_wires_sse(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'sse-connect="/stream"' in response.text


class TestAskTemplateStream:
    """/ask returns a TemplateStream — chunked HTML from {% async for %}."""

    async def test_ask_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": "What is Chirp?"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200

    async def test_ask_streams_simulated_reply(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": "Hello"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "You asked: Hello" in response.text
            assert "still just Python" in response.text

    async def test_ask_defaults_blank_prompt(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": ""},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "What is Chirp?" in response.text


class TestStreamEventStream:
    """/stream returns an EventStream — one Fragment per token + a close event."""

    async def test_stream_is_event_stream(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream", max_events=100)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"

    async def test_stream_tokens_are_rendered_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream", max_events=100)

        token_events = [e for e in result.events if (e.event or "message") == "message"]
        assert token_events  # at least one token streamed
        joined = "".join(e.data for e in token_events)
        assert "You asked" in joined
        assert "<span>" in joined  # rendered the {% block token %}, not raw template
        assert "{{" not in joined

    async def test_stream_closes_cleanly(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream", max_events=100)
        assert result.events[-1].event == "close"


class TestSSEWiring:
    """Page sse-swap channel and the stream's event names agree."""

    async def test_wiring(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await assert_sse_wired(client, "/", "/stream", max_events=100)

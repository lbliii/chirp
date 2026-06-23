"""Tests for llm_minimal — simulated streaming, no Ollama or API keys.

Covers both streaming paths the README compares:
- ``/ask``    — TemplateStream (full-page chunked HTML body)
- ``/stream`` — EventStream (one SSE Fragment per token)
"""

import re

import pytest

from chirp.testing import TestClient, extract_sse_attrs


class TestIndex:
    """The form page renders and wires up both streaming paths."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_has_template_stream_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'action="/ask"' in response.text
            assert 'method="post"' in response.text
            assert 'hx-post="/ask"' not in response.text

    async def test_index_has_sse_start_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'hx-post="/stream/start"' in response.text
            assert 'hx-target="#sse-section"' in response.text


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
            assert "<html" in response.text.lower()

    async def test_ask_defaults_blank_prompt(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": ""},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "What is Chirp?" in response.text


class TestStreamStart:
    """POST /stream/start returns an SSE panel fragment for the submitted prompt."""

    async def test_stream_start_returns_sse_panel(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/stream/start",
                data={"prompt": "Hello"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Request": "true",
                },
            )
            assert response.status == 200
            assert 'sse-connect="/stream?prompt=Hello"' in response.text
            assert 'hx-swap="beforeend"' in response.text
            assert "Prompt: Hello" in response.text
            assert "<html" not in response.text.lower()


class TestStreamEventStream:
    """/stream returns an EventStream — one Fragment per token + a close event."""

    async def test_stream_is_event_stream(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream?prompt=Hello", max_events=100)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"

    async def test_stream_tokens_are_rendered_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream?prompt=Hello", max_events=100)

        token_events = [e for e in result.events if (e.event or "message") == "message"]
        assert token_events  # at least one token streamed
        joined = "".join(e.data for e in token_events)
        plain = re.sub(r"<[^>]+>", "", joined)
        assert "You asked: Hello" in plain
        assert "<span>" in joined  # rendered the {% block token %}, not raw template
        assert "{{" not in joined

    async def test_stream_closes_cleanly(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/stream?prompt=Hello", max_events=100)
        assert result.events[-1].event == "close"


class TestSSEWiring:
    """Fragment sse-connect URL and the stream's event names agree."""

    async def test_wiring_after_stream_start(self, example_app) -> None:
        async with TestClient(example_app) as client:
            panel = await client.post(
                "/stream/start",
                data={"prompt": "Hello"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Request": "true",
                },
            )
            connects, swaps = extract_sse_attrs(panel.text)
            assert connects == ["/stream?prompt=Hello"]
            assert "message" in swaps
            result = await client.sse(connects[0], max_events=100)
            emitted = {evt.event or "message" for evt in result.events}
            assert not (swaps - emitted)


@pytest.mark.issue(454)
class TestIssue454Acceptance:
    """Acceptance for #454 — minimal standalone streaming LLM example."""

    async def test_simulated_stream_without_ollama(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.post(
                "/ask",
                data={"prompt": "What is Chirp?"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "still just Python" in page.text

            panel = await client.post(
                "/stream/start",
                data={"prompt": "What is Chirp?"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Request": "true",
                },
            )
            assert 'sse-connect="/stream?prompt=What%20is%20Chirp%3F"' in panel.text

            stream = await client.sse("/stream?prompt=What%20is%20Chirp%3F", max_events=100)
            assert stream.events[-1].event == "close"

"""Tests for the SSE example — real-time event streaming."""

from chirp.testing import TestClient


class TestSSEFeedPage:
    """The page shell renders correctly."""

    async def test_index_renders_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html>" in response.text
            assert "<h1>Live Feed</h1>" in response.text
            assert 'sse-connect="/events"' in response.text


class TestSSEEventStream:
    """Events stream through the full pipeline."""

    async def test_collects_all_events(self, example_app) -> None:
        """The generator yields 1 string + 1 SSEEvent + 4 Fragments = 6 total."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) == 6

    async def test_first_event_is_string(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        first = result.events[0]
        assert first.data == "connected"
        assert first.event is None  # plain string, no event type

    async def test_second_event_is_structured(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        second = result.events[1]
        assert second.data == "heartbeat check"
        assert second.event == "status"
        assert second.id == "1"

    async def test_fragment_events_contain_rendered_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        # Events 2-5 are Fragments (rendered via kida)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        assert len(fragment_events) == 4

        # Each fragment should contain rendered HTML, not template syntax
        for evt in fragment_events:
            assert '<div class="notification">' in evt.data
            assert "{{" not in evt.data  # no raw template tags

    async def test_fragment_content_matches_notifications(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        fragment_events = [e for e in result.events if e.event == "fragment"]
        assert "Welcome" in fragment_events[0].data
        assert "New deployment started" in fragment_events[1].data
        assert "CPU usage above 90%" in fragment_events[2].data
        assert "back to normal" in fragment_events[3].data

    async def test_stream_closes_when_generator_exhausts(self, example_app) -> None:
        """Asking for more events than the generator yields closes cleanly."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=20)

        # Generator only yields 6, so we get exactly 6
        assert len(result.events) == 6

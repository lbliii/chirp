"""Tests for the dashboard example — full stack showcase."""

from chirp.testing import TestClient


class TestDashboardPage:
    """The initial page renders all sensor cards via streaming."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_contains_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Weather Station" in response.text

    async def test_index_renders_all_sensors(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            for sensor_id in ("rooftop", "garden", "lakeside", "hilltop", "warehouse", "parking"):
                assert f"sensor-{sensor_id}" in response.text

    async def test_index_renders_summary_bar(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="summary"' in response.text
            assert "Avg temp:" in response.text
            assert "Max wind:" in response.text

    async def test_index_contains_sse_connection(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'sse-connect="/events"' in response.text


class TestDashboardSSE:
    """Live sensor updates stream through the SSE pipeline."""

    async def test_receives_events(self, example_app) -> None:
        """Each tick yields 2 events (sensor card + summary bar)."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 2

    async def test_events_are_fragments(self, example_app) -> None:
        """Fragment events contain rendered HTML, not template syntax."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        assert len(fragment_events) >= 2
        for evt in fragment_events:
            assert "{{" not in evt.data  # no raw template tags

    async def test_sensor_card_has_oob_swap(self, example_app) -> None:
        """Sensor card fragments include hx-swap-oob for targeted updates."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        # At least one fragment should have hx-swap-oob (the sensor card)
        oob_events = [e for e in fragment_events if "hx-swap-oob" in e.data]
        assert len(oob_events) >= 1

    async def test_summary_bar_updates(self, example_app) -> None:
        """Summary bar fragment includes aggregate stats."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        summary_events = [e for e in fragment_events if 'id="summary"' in e.data]
        assert len(summary_events) >= 1
        assert "Avg temp:" in summary_events[0].data

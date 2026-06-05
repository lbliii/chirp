"""Tests for the SSE reconnect example — app-owned-cursor recovery.

Proves the bright line: the framework only READS and EXPOSES Last-Event-ID.
Recovery is the app's query against its own event log. A fresh connection gets
the full log; a reconnect with Last-Event-ID gets only the missed gap.
"""

from chirp.testing import TestClient, assert_sse_wired


class TestFeedPage:
    """The page shell renders and is wired for the deploy channel."""

    async def test_index_renders_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<h1>Deploy Feed</h1>" in response.text
            assert 'sse-connect="/events"' in response.text
            assert 'sse-swap="deploy"' in response.text


class TestFreshConnection:
    """A fresh tab (no Last-Event-ID) receives the entire log."""

    async def test_fresh_connection_replays_full_log(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # 5 deploy events + 1 close event.
            result = await client.sse("/events", max_events=6)

        deploy = [e for e in result.events if e.event == "deploy"]
        assert [e.id for e in deploy] == ["1", "2", "3", "4", "5"]
        assert result.events[-1].event == "close"

    async def test_events_carry_rendered_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=6)

        deploy = [e for e in result.events if e.event == "deploy"]
        assert '<div class="deploy-event">' in deploy[0].data
        assert "Deploy queued" in deploy[0].data
        assert "{{" not in deploy[0].data  # rendered, not raw template


class TestReconnectRecovery:
    """A reconnect replays only the events past the client's cursor."""

    async def test_reconnect_replays_only_missed_events(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # First connection drops after seeing events 1 and 2.
            first = await client.sse("/events", max_events=2)
            # The browser's cursor only advances on events that carry an id;
            # the last id seen is the last deploy event's id.
            last_id = [e.id for e in first.events if e.event == "deploy"][-1]

            # Browser reconnects, resending the last id it saw.
            reconnect = await client.sse(
                "/events",
                headers={"Last-Event-ID": last_id},
                max_events=10,
            )

        assert [e.id for e in first.events if e.event == "deploy"] == ["1", "2"]
        replayed = [e for e in reconnect.events if e.event == "deploy"]
        assert [e.id for e in replayed] == ["3", "4", "5"]

    async def test_reconnect_at_end_replays_nothing(self, example_app) -> None:
        """If the client already saw everything, recovery yields no events."""
        async with TestClient(example_app) as client:
            reconnect = await client.sse(
                "/events",
                headers={"Last-Event-ID": "5"},
                max_events=10,
            )

        replayed = [e for e in reconnect.events if e.event == "deploy"]
        assert replayed == []
        # Only the close event is sent.
        assert reconnect.events[-1].event == "close"

    async def test_garbage_last_event_id_starts_from_beginning(self, example_app) -> None:
        """A malformed cursor is treated as a fresh connection (id 0)."""
        async with TestClient(example_app) as client:
            result = await client.sse(
                "/events",
                headers={"Last-Event-ID": "not-a-number"},
                max_events=6,
            )

        deploy = [e for e in result.events if e.event == "deploy"]
        assert [e.id for e in deploy] == ["1", "2", "3", "4", "5"]


class TestWiring:
    """Page markup and stream event names agree."""

    async def test_wiring(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await assert_sse_wired(client, "/", "/events", max_events=6)

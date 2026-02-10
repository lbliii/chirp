"""Integration tests for SSE through the full App → ASGI → handle_sse pipeline.

These tests exercise the complete SSE lifecycle: route handler returns
EventStream, content negotiation wraps it in SSEResponse, the ASGI handler
dispatches to handle_sse(), and the TestClient collects structured events.
"""

import json
from pathlib import Path

import pytest

from chirp.app import App
from chirp.config import AppConfig
from chirp.realtime.events import EventStream, SSEEvent
from chirp.templating.returns import Fragment
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _app(**overrides: object) -> App:
    """Build an app wired to the test templates directory."""
    cfg = AppConfig(template_dir=TEMPLATES_DIR, **overrides)
    return App(config=cfg)


# ---------------------------------------------------------------------------
# Basic event streaming
# ---------------------------------------------------------------------------


class TestBasicSSEStreaming:
    """String events through the full pipeline."""

    async def test_string_events(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "alpha"
                yield "beta"
                yield "gamma"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=3)

        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert result.headers.get("cache-control") == "no-cache"
        assert len(result.events) == 3
        assert result.events[0].data == "alpha"
        assert result.events[1].data == "beta"
        assert result.events[2].data == "gamma"

    async def test_finite_generator_closes_cleanly(self) -> None:
        """When the generator is exhausted, the stream closes without error."""
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "only-one"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=10)

        # Only 1 event yielded despite max_events=10
        assert len(result.events) == 1
        assert result.events[0].data == "only-one"

    async def test_default_event_type(self) -> None:
        """EventStream.event_type is applied to all string events."""
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "hello"

            return EventStream(gen(), event_type="update")

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        assert result.events[0].event == "update"
        assert result.events[0].data == "hello"

    async def test_configured_retry_metadata_event(self) -> None:
        app = App(config=AppConfig(sse_retry_ms=900))

        @app.route("/events")
        def events():
            async def gen():
                yield "payload"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=2)

        assert len(result.events) == 2
        assert result.events[0].event == "chirp:sse:meta"
        assert result.events[0].retry == 900
        assert result.events[1].data == "payload"

    async def test_configured_close_event(self) -> None:
        app = App(config=AppConfig(sse_close_event="done"))

        @app.route("/events")
        def events():
            async def gen():
                yield "payload"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=2)

        assert len(result.events) == 2
        assert result.events[0].data == "payload"
        assert result.events[1].event == "done"


# ---------------------------------------------------------------------------
# SSEEvent passthrough
# ---------------------------------------------------------------------------


class TestSSEEventPassthrough:
    """Yielding SSEEvent objects preserves all fields."""

    async def test_sse_event_with_all_fields(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield SSEEvent(data="payload", event="custom", id="42", retry=5000)

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        evt = result.events[0]
        assert evt.data == "payload"
        assert evt.event == "custom"
        assert evt.id == "42"
        assert evt.retry == 5000

    async def test_sse_event_data_only(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield SSEEvent(data="simple")

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        assert result.events[0].data == "simple"
        assert result.events[0].event is None

    async def test_multiline_data(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield SSEEvent(data="line1\nline2\nline3")

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        assert result.events[0].data == "line1\nline2\nline3"


# ---------------------------------------------------------------------------
# Dict / JSON events
# ---------------------------------------------------------------------------


class TestDictEvents:
    """Dicts are JSON-serialized as SSE data."""

    async def test_dict_event(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield {"user": "alice", "action": "login"}

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        parsed = json.loads(result.events[0].data)
        assert parsed == {"user": "alice", "action": "login"}


# ---------------------------------------------------------------------------
# Fragment rendering in SSE
# ---------------------------------------------------------------------------


class TestFragmentSSE:
    """Fragment objects are rendered via kida and sent with event: fragment."""

    async def test_fragment_event(self) -> None:
        app = _app()

        @app.route("/events")
        def events():
            async def gen():
                yield Fragment("search.html", "results_list", results=["x", "y"])

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        evt = result.events[0]
        assert evt.event == "fragment"
        assert '<div id="results">' in evt.data
        assert "x" in evt.data
        assert "y" in evt.data


# ---------------------------------------------------------------------------
# Disconnect handling
# ---------------------------------------------------------------------------


class TestSSEDisconnect:
    """Client disconnect terminates the stream cleanly."""

    async def test_disconnect_during_pending_anext_no_warnings(
        self, recwarn,
    ) -> None:
        """Disconnect while __anext__ is pending must not leak StopAsyncIteration.

        Previously, the pending_next task cleanup was inside the try block and
        skipped when CancelledError jumped to the except handler. The orphaned
        task's StopAsyncIteration went unretrieved, producing a noisy warning.
        """
        import asyncio
        import warnings

        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "first"
                # Block long enough for the client to disconnect
                await asyncio.sleep(10)
                yield "never-sent"

            return EventStream(gen())

        # Capture warnings at runtime
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            async with TestClient(app) as client:
                result = await client.sse("/events", disconnect_after=0.15)

        assert len(result.events) >= 1
        assert result.events[0].data == "first"

        # No StopAsyncIteration warnings should have been logged
        stop_warnings = [
            w for w in caught if "StopAsyncIteration" in str(w.message)
        ]
        assert stop_warnings == [], (
            f"Unexpected StopAsyncIteration warnings: {stop_warnings}"
        )

    async def test_disconnect_after_n_events(self) -> None:
        """Infinite generator, but client disconnects after 3 events."""
        app = App()
        yielded_count = 0

        @app.route("/events")
        def events():
            async def gen():
                nonlocal yielded_count
                counter = 0
                while True:
                    counter += 1
                    yielded_count = counter
                    yield f"event-{counter}"

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=3)

        assert len(result.events) == 3
        assert result.events[0].data == "event-1"
        assert result.events[1].data == "event-2"
        assert result.events[2].data == "event-3"

    async def test_disconnect_after_timeout(self) -> None:
        """Slow generator, disconnect after a short timeout."""
        app = App()

        @app.route("/events")
        def events():
            import asyncio

            async def gen():
                counter = 0
                while True:
                    counter += 1
                    yield f"tick-{counter}"
                    await asyncio.sleep(0.05)

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", disconnect_after=0.2)

        # Should have collected some events in ~0.2s at 50ms intervals
        assert len(result.events) >= 1
        assert result.events[0].data == "tick-1"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestSSEHeartbeat:
    """Heartbeat comments are sent on idle and counted."""

    @pytest.mark.slow
    async def test_heartbeat_on_slow_generator(self) -> None:
        """With a very short heartbeat interval, heartbeats arrive between events."""
        app = App()

        @app.route("/events")
        def events():
            import asyncio

            async def gen():
                await asyncio.sleep(0.3)
                yield "done"

            return EventStream(gen(), heartbeat_interval=0.1)

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=1)

        assert len(result.events) == 1
        assert result.events[0].data == "done"
        # With 0.3s sleep and 0.1s heartbeat, expect ~2 heartbeats
        assert result.heartbeats >= 1


# ---------------------------------------------------------------------------
# Error in generator
# ---------------------------------------------------------------------------


class TestSSEGeneratorError:
    """Generator errors close the stream gracefully."""

    async def test_generator_raises_after_events(self) -> None:
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "ok-1"
                yield "ok-2"
                msg = "generator failed"
                raise RuntimeError(msg)

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=10)

        # Should have collected the events before the error
        assert len(result.events) >= 2
        assert result.events[0].data == "ok-1"
        assert result.events[1].data == "ok-2"

    async def test_generator_error_sends_error_event(self) -> None:
        """SSE error event is sent when the generator raises."""
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "before"
                msg = "boom"
                raise RuntimeError(msg)

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=10, disconnect_after=2.0)

        # Find the error event among collected events
        error_events = [e for e in result.events if e.event == "error"]
        assert len(error_events) >= 1
        assert "Internal server error" in error_events[0].data

    async def test_generator_error_logs_exception(self, caplog) -> None:
        """SSE generator errors are logged via logger.exception()."""
        app = App()

        @app.route("/events")
        def events():
            async def gen():
                yield "before"
                msg = "sse log test"
                raise RuntimeError(msg)

            return EventStream(gen())

        with caplog.at_level("ERROR", logger="chirp.server"):
            async with TestClient(app) as client:
                await client.sse("/events", max_events=10, disconnect_after=2.0)

        # log_error() formats with compact traceback including error type
        assert any("RuntimeError" in r.message for r in caplog.records)

    async def test_debug_mode_error_includes_traceback(self) -> None:
        """Debug mode SSE error events include the full traceback."""
        app = App(config=AppConfig(debug=True))

        @app.route("/events")
        def events():
            async def gen():
                yield "before-error"
                msg = "debug sse error"
                raise RuntimeError(msg)

            return EventStream(gen())

        async with TestClient(app) as client:
            result = await client.sse("/events", max_events=10, disconnect_after=2.0)

        error_events = [e for e in result.events if e.event == "error"]
        assert len(error_events) >= 1
        # Debug mode includes the traceback with "RuntimeError" and the message
        assert "RuntimeError" in error_events[0].data
        assert "debug sse error" in error_events[0].data

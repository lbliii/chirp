"""Tests for chirp.realtime.events — SSEEvent and EventStream."""

import pytest

from chirp.realtime.events import EventStream, SSEEvent


class TestSSEEvent:
    def test_data_only(self) -> None:
        e = SSEEvent(data="hello")
        encoded = e.encode()
        assert encoded == "data: hello\n\n"

    def test_with_event_type(self) -> None:
        e = SSEEvent(data="payload", event="fragment")
        encoded = e.encode()
        assert "event: fragment\n" in encoded
        assert "data: payload\n" in encoded

    def test_with_id(self) -> None:
        e = SSEEvent(data="payload", id="42")
        assert "id: 42\n" in e.encode()

    def test_with_retry(self) -> None:
        e = SSEEvent(data="payload", retry=5000)
        assert "retry: 5000\n" in e.encode()

    def test_multiline_data(self) -> None:
        e = SSEEvent(data="line1\nline2\nline3")
        encoded = e.encode()
        assert "data: line1\n" in encoded
        assert "data: line2\n" in encoded
        assert "data: line3\n" in encoded

    def test_all_fields(self) -> None:
        e = SSEEvent(data="msg", event="update", id="7", retry=3000)
        encoded = e.encode()
        # Fields appear in order: event, id, retry, data
        lines = encoded.strip().split("\n")
        assert lines[0] == "event: update"
        assert lines[1] == "id: 7"
        assert lines[2] == "retry: 3000"
        assert lines[3] == "data: msg"

    def test_frozen(self) -> None:
        e = SSEEvent(data="hello")
        with pytest.raises(AttributeError):
            e.data = "other"  # type: ignore[misc]


class TestEventStream:
    def test_defaults(self) -> None:
        async def gen():
            yield "hello"

        es = EventStream(generator=gen())
        assert es.event_type is None
        assert es.heartbeat_interval == 15.0

    def test_custom_config(self) -> None:
        async def gen():
            yield "hello"

        es = EventStream(generator=gen(), event_type="fragment", heartbeat_interval=5.0)
        assert es.event_type == "fragment"
        assert es.heartbeat_interval == 5.0

    def test_frozen(self) -> None:
        async def gen():
            yield "hello"

        es = EventStream(generator=gen())
        with pytest.raises(AttributeError):
            es.heartbeat_interval = 1.0  # type: ignore[misc]

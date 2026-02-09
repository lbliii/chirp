"""Tests for the SSE frame parser in chirp.testing.sse."""

from chirp.testing.sse import parse_sse_frames


class TestParseSSEFrames:
    """Unit tests for parse_sse_frames()."""

    def test_single_data_event(self) -> None:
        raw = "data: hello\n\n"
        events, heartbeats = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].data == "hello"
        assert events[0].event is None
        assert heartbeats == 0

    def test_event_with_type(self) -> None:
        raw = "event: fragment\ndata: <div>hi</div>\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].event == "fragment"
        assert events[0].data == "<div>hi</div>"

    def test_multiple_events(self) -> None:
        raw = "data: first\n\ndata: second\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 2
        assert events[0].data == "first"
        assert events[1].data == "second"

    def test_multiline_data(self) -> None:
        raw = "data: line1\ndata: line2\ndata: line3\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].data == "line1\nline2\nline3"

    def test_trailing_whitespace_preserved_in_data(self) -> None:
        """Regression: block.strip() must not eat significant trailing spaces."""
        raw = "event: fragment\ndata: Hi \n\nevent: fragment\ndata: there!\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 2
        assert events[0].data == "Hi "
        assert events[1].data == "there!"
        text = "".join(e.data for e in events)
        assert text == "Hi there!"

    def test_heartbeat_comments(self) -> None:
        raw = ": heartbeat\n\ndata: payload\n\n: heartbeat\n\n"
        events, heartbeats = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].data == "payload"
        assert heartbeats == 2

    def test_event_with_id(self) -> None:
        raw = "id: 42\ndata: msg\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].id == "42"
        assert events[0].data == "msg"

    def test_event_with_retry(self) -> None:
        raw = "retry: 3000\ndata: reconnect\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].retry == 3000

    def test_empty_input(self) -> None:
        events, heartbeats = parse_sse_frames("")
        assert events == []
        assert heartbeats == 0

    def test_only_heartbeats(self) -> None:
        raw = ": heartbeat\n\n: heartbeat\n\n"
        events, heartbeats = parse_sse_frames(raw)
        assert events == []
        assert heartbeats == 2

    def test_inline_heartbeat_within_block(self) -> None:
        """Heartbeat comment line within an event block is counted."""
        raw = "event: msg\n: heartbeat\ndata: hello\n\n"
        events, heartbeats = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].data == "hello"
        assert heartbeats == 1

    def test_invalid_retry_ignored(self) -> None:
        raw = "retry: not-a-number\ndata: still-ok\n\n"
        events, _ = parse_sse_frames(raw)
        assert len(events) == 1
        assert events[0].retry is None
        assert events[0].data == "still-ok"

"""Tests for streaming HTML injection (bounded buffer before ``</body>``)."""

from chirp.middleware.streaming_html import async_stream_inject_before_body


class TestAsyncStreamInjectBeforeBody:
    async def test_injects_before_first_body_close(self) -> None:
        async def chunks() -> object:
            yield "<html><body>x"
            yield "</body></html>"

        out = [
            part
            async for part in async_stream_inject_before_body(
                chunks(),
                snippet="<!--SNIP-->",
                before="</body>",
                dedup_marker=None,
                full_page_only=True,
            )
        ]
        assert "".join(out) == "<html><body>x<!--SNIP--></body></html>"

    async def test_handles_delimiter_split_across_chunks(self) -> None:
        async def chunks() -> object:
            yield "<html><body><p>z</p></bo"
            yield "dy></html>"

        out = [
            part
            async for part in async_stream_inject_before_body(
                chunks(),
                snippet="I",
                before="</body>",
                dedup_marker=None,
                full_page_only=True,
            )
        ]
        assert "".join(out) == "<html><body><p>z</p>I</body></html>"

    async def test_sync_iterator_wrapped(self) -> None:
        def sync_chunks():
            yield "<html><body>a"
            yield "</body></html>"

        out = [
            part
            async for part in async_stream_inject_before_body(
                sync_chunks(),
                snippet="S",
                before="</body>",
                dedup_marker=None,
                full_page_only=True,
            )
        ]
        assert "".join(out) == "<html><body>aS</body></html>"

    async def test_dedup_skips_when_marker_before_body(self) -> None:
        async def chunks() -> object:
            yield '<html><body data-chirp="alpine" x'
            yield "</body></html>"

        out = [
            part
            async for part in async_stream_inject_before_body(
                chunks(),
                snippet="SHOULD_NOT",
                before="</body>",
                dedup_marker='data-chirp="alpine"',
                full_page_only=True,
            )
        ]
        joined = "".join(out)
        assert "SHOULD_NOT" not in joined
        assert 'data-chirp="alpine"' in joined

    async def test_dedup_waits_for_body_to_compare_order(self) -> None:
        """Marker in buffer before </body> arrives — must not skip early."""

        async def chunks() -> object:
            yield "<html><body><p>later</p>"
            yield '<script data-chirp="alpine"></script>'
            yield "</body></html>"

        out = [
            part
            async for part in async_stream_inject_before_body(
                chunks(),
                snippet="INJ",
                before="</body>",
                dedup_marker='data-chirp="alpine"',
                full_page_only=True,
            )
        ]
        joined = "".join(out)
        assert "INJ" not in joined
        assert joined.count('data-chirp="alpine"') == 1

    async def test_collect_runs(self) -> None:
        async def ch():
            yield "a</bo"
            yield "dy>"

        parts = [
            p
            async for p in async_stream_inject_before_body(
                ch(), snippet="X", before="</body>", dedup_marker=None, full_page_only=True
            )
        ]
        assert "".join(parts) == "aX</body>"


async def test_alpine_middleware_wraps_streaming_response() -> None:
    """AlpineInject rewrites StreamingResponse chunks (same as Suspense output)."""
    from chirp.http.response import StreamingResponse
    from chirp.middleware.inject import AlpineInject
    from chirp.server.alpine import alpine_snippet

    class FakeRequest:
        is_fragment = False

    snippet = alpine_snippet("3.15.8", csp=False)
    mw = AlpineInject(snippet, full_page_only=True)

    async def next_ok(_req: object) -> StreamingResponse:
        def chunks():
            yield "<!DOCTYPE html><html><head></head><body>ok"
            yield "</body></html>"

        return StreamingResponse(chunks=chunks())

    resp = await mw(FakeRequest(), next_ok)
    assert isinstance(resp, StreamingResponse)
    parts: list[str] = [chunk async for chunk in resp.chunks]
    text = "".join(parts)
    assert 'data-chirp="alpine"' in text
    assert "cdn.jsdelivr.net/npm/alpinejs" in text
    assert "_chirpAlpineData" in text


async def test_streaming_html_inject_wraps_streaming_response() -> None:
    """StreamingHTMLInject rewrites StreamingResponse chunks for full-page HTML."""
    from chirp.http.response import StreamingResponse
    from chirp.middleware.inject import StreamingHTMLInject

    class FakeRequest:
        is_fragment = False

    snippet = '<script data-chirp="chirpui-alpine" src="/static/chirpui-alpine.js"></script>'
    mw = StreamingHTMLInject(
        snippet,
        before="</head>",
        full_page_only=True,
        dedup_marker='data-chirp="chirpui-alpine"',
    )

    async def next_ok(_req: object) -> StreamingResponse:
        def chunks():
            yield "<!DOCTYPE html><html><head><title>x</title></head><body>ok"
            yield "</body></html>"

        return StreamingResponse(chunks=chunks())

    resp = await mw(FakeRequest(), next_ok)
    assert isinstance(resp, StreamingResponse)
    parts: list[str] = [chunk async for chunk in resp.chunks]
    text = "".join(parts)
    assert 'data-chirp="chirpui-alpine"' in text
    assert "</script></head>" in text

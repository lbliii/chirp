"""Tests for streaming HTML injection and Stream off-loop rendering."""

import threading
import time

import anyio
import pytest
from kida import DictLoader, Environment
from kida.exceptions import TemplateRuntimeError

from chirp.middleware.streaming_html import async_stream_inject_before_body
from chirp.templating.returns import Stream
from chirp.templating.streaming import render_stream_async


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
        is_htmx = False

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
        is_htmx = False

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


# ---------------------------------------------------------------------------
# Stream off-loop rendering (issue #179): thread + bounded-queue bridge.
#
# render_stream_async drives kida's CPU-bound sync render generator on a worker
# thread, bridging chunks back to the loop through a bounded queue. These tests
# prove the four acceptance criteria:
#   1. a slow Stream render does NOT block concurrent loop tasks
#   2. progressive flush is preserved (chunks arrive incrementally)
#   3. client disconnect (early aclose) does not leak the worker thread
#   4. a mid-stream render error surfaces to the consumer (sender.py error path)
# ---------------------------------------------------------------------------

_SLOW_TEMPLATE = "<p>{{ x }}</p>{% for i in items %}<li>{{ slow(i) }}</li>{% end %}"
_ERR_TEMPLATE = "<p>start</p>{% for i in items %}<li>{{ boom(i) }}</li>{% end %}"
_RENDER_THREAD_NAME = "chirp-stream-render"


def _slow_env(sleep_s: float = 0.03) -> Environment:
    """Environment whose render blocks per item (simulates CPU-bound render)."""
    env = Environment(loader=DictLoader({"slow.html": _SLOW_TEMPLATE, "err.html": _ERR_TEMPLATE}))

    def slow(i: int) -> int:
        time.sleep(sleep_s)
        return i

    def boom(i: int) -> int:
        if i == 2:
            raise ValueError("mid-stream boom")
        return i

    env.add_global("slow", slow)
    env.add_global("boom", boom)
    return env


def _render_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == _RENDER_THREAD_NAME and t.is_alive()]


async def test_slow_stream_does_not_block_concurrent_tasks() -> None:
    """A slow/CPU-bound Stream render must not block concurrent loop tasks.

    While the Stream renders (each item sleeps on a worker thread), a
    concurrent loop task increments a counter. The counter must advance before
    the Stream finishes — proving the loop is free, not blocked on the render.
    """
    env = _slow_env(sleep_s=0.02)
    stream = Stream("slow.html", x="hi", items=list(range(10)))

    counter = {"n": 0}

    async def ticker() -> None:
        while True:
            counter["n"] += 1
            await anyio.sleep(0.002)

    chunks: list[str] = []
    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        chunks = [chunk async for chunk in render_stream_async(env, stream)]
        tg.cancel_scope.cancel()

    assert "".join(chunks) == "<p>hi</p>" + "".join(f"<li>{i}</li>" for i in range(10))
    # ~0.2s of render time; a non-blocked loop ticks many times. If the render
    # ran inline on the loop, the ticker could not advance at all.
    assert counter["n"] > 10, f"loop appears blocked: ticker only advanced {counter['n']}"


async def test_progressive_flush_chunks_arrive_incrementally() -> None:
    """Chunks must arrive spread over time, not buffered then flushed at once."""
    env = _slow_env(sleep_s=0.02)
    stream = Stream("slow.html", x="hi", items=list(range(5)))

    t0 = time.monotonic()
    arrival = [time.monotonic() - t0 async for _chunk in render_stream_async(env, stream)]

    assert len(arrival) > 1
    # The first chunk arrives well before the last (progressive), and the
    # spread is non-trivial relative to the per-item sleep — a buffer-then-flush
    # implementation would deliver all chunks at roughly the same instant.
    spread = arrival[-1] - arrival[0]
    assert spread > 0.02, f"chunks not progressive (spread={spread:.4f}s)"
    assert arrival[0] < arrival[-1]


async def test_disconnect_early_aclose_does_not_leak_worker_thread() -> None:
    """Early aclose (client disconnect) must join the render thread, no leak."""
    env = _slow_env(sleep_s=0.02)
    stream = Stream("slow.html", x="hi", items=list(range(100)))

    before = set(threading.enumerate())
    gen = render_stream_async(env, stream)
    first = await gen.__anext__()
    assert first == "<p>hi</p>"
    # Worker thread is running mid-render.
    assert _render_threads(), "expected a running render worker thread"

    # Simulate client disconnect: close the consumer early.
    await gen.aclose()

    # The render worker must have been joined — no leaked thread past aclose().
    assert _render_threads() == [], "render worker thread leaked after aclose()"
    leaked = {t for t in threading.enumerate() if t.name == _RENDER_THREAD_NAME} - before
    assert not leaked, f"leaked render threads: {leaked}"


async def test_mid_stream_error_propagates_to_consumer() -> None:
    """A render error raised mid-stream must surface to the consumer.

    This preserves sender.py's mid-stream error path: the exception is raised on
    the loop after the worker exits, with the chunks emitted before the failure
    already delivered.
    """
    env = _slow_env(sleep_s=0.0)
    stream = Stream("err.html", items=[1, 2, 3])

    chunks: list[str] = []

    async def _consume() -> None:
        # Collect incrementally so chunks emitted before the failure are
        # captured even when the consume raises mid-stream.
        async for chunk in render_stream_async(env, stream):
            chunks.append(chunk)  # noqa: PERF401

    with pytest.raises(TemplateRuntimeError):
        await _consume()

    # Chunks before the failing item were delivered (progressive, not buffered).
    assert "<p>start</p>" in chunks
    assert "1" in chunks
    # And the worker thread did not leak on the error path either.
    assert _render_threads() == [], "render worker thread leaked after error"

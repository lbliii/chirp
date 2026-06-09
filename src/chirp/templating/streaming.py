"""Async stream orchestration for progressive rendering.

When a ``Stream()`` return value contains awaitables (coroutines) in its
context, this module resolves them concurrently using anyio, then feeds
the resolved context to kida's synchronous ``render_stream()`` for
progressive chunk delivery.

This is Chirp-level orchestration around existing Kida primitives —
no changes to Kida's rendering engine required.

Pipeline::

    Stream("page.html",
        header=site_header(),        # already resolved (str)
        stats=db.fetch(Stats, ..),   # awaitable (coroutine)
        feed=db.fetch(Event, ..),    # awaitable (coroutine)
    )

    1. Detect awaitables in context
    2. Resolve all awaitables concurrently (anyio.create_task_group)
    3. Drive kida's lazy sync render_stream() on a worker thread, bridging
       each chunk back to the loop through a bounded queue
    4. Yield HTML chunks via chunked transfer encoding

Thread + bounded-queue bridge (issue #179):
    kida's ``render_stream()`` is a CPU-bound *synchronous* generator. Iterating
    it inline on the event loop blocks every concurrent request for the duration
    of each chunk's compilation. It also cannot simply be wrapped in
    ``anyio.to_thread.run_sync`` — that runs a callable to *completion*, which
    would buffer the whole render and defeat progressive flush.

    Instead a dedicated worker thread drives the generator chunk-by-chunk and
    hands each chunk to the loop through a bounded ``queue.Queue``
    (``_STREAM_CHUNK_BUFFER`` rendered chunks in flight, plus one reserved slot
    for the terminal sentinel). The loop pulls each chunk via
    ``anyio.to_thread.run_sync(queue.get)``, so that ``await`` lets concurrent
    tasks make progress while the worker computes the next chunk, and the
    bounded queue applies back-pressure (the worker blocks in ``put`` when the
    loop is slow), keeping memory bounded. The kida template and its generator
    are *both created and driven on the same worker thread* — never created on
    the loop and iterated on the worker — to respect kida's single-thread
    renderer contract. No anyio task group or portal wraps the ``yield``, so a
    consumer ``aclose()`` (``GeneratorExit``) unwinds cleanly rather than being
    wrapped into a noisy ``ExceptionGroup``.

    Cancellation contract: on client disconnect / consumer ``aclose()`` the
    shielded ``finally`` block sets a stop event and drains the queue so the
    worker's blocked ``put`` unwinds, then joins the worker thread to
    completion. The thread cannot leak past the async generator's ``aclose()``.

    A mid-stream render error is captured on the worker thread and re-raised on
    the loop after the worker exits, so ``sender.py``'s mid-stream error path
    still fires.

Shell-first streaming (kida 0.2.3+):
    Use ``{% flush %}`` in templates to emit a streaming boundary. Place it
    after header/nav so the client receives the shell before main content::

        <html><head>...</head><body>
        <header>...</header><nav>...</nav>
        {% flush %}
        <main>{% for item in items %}...{% end %}</main>
        </body></html>
"""

import contextlib
import inspect
import queue
import threading
from collections.abc import AsyncIterator, Awaitable, Iterator
from typing import Any

import anyio
import anyio.to_thread
from kida import Environment

from chirp.templating.returns import Stream

# Bounded buffer between the render worker thread and the loop consumer.
# A size of 0 gives rendezvous semantics (closest to the old inline flush:
# the worker blocks until the loop takes each chunk), preserving true
# progressive flush and bounding memory to a single in-flight chunk. This is
# an internal tuning constant, not a public AppConfig knob.
_STREAM_CHUNK_BUFFER = 0


async def resolve_stream_context(context: dict[str, Any]) -> dict[str, Any]:
    """Resolve any awaitables in a Stream() context concurrently.

    Values that are coroutines or awaitables are resolved in parallel.
    All other values pass through unchanged.

    Returns a new dict with all values fully resolved.
    """
    resolved: dict[str, Any] = {}
    pending: dict[str, Awaitable[Any]] = {}

    for key, value in context.items():
        if inspect.isawaitable(value):
            pending[key] = value
        else:
            resolved[key] = value

    if not pending:
        return resolved

    # Resolve all awaitables concurrently
    results: dict[str, Any] = {}

    async def _resolve(key: str, awaitable: Awaitable[Any]) -> None:
        results[key] = await awaitable

    async with anyio.create_task_group() as tg:
        for key, awaitable in pending.items():
            tg.start_soon(_resolve, key, awaitable)

    resolved.update(results)
    return resolved


# Sentinels distinguishing the queue's control messages from rendered chunks.
class _StreamSentinel:
    __slots__ = ()


_STREAM_END = _StreamSentinel()  # producer finished (normal or error)


async def render_stream_async(
    env: Environment,
    stream: Stream,
) -> AsyncIterator[str]:
    """Render a Stream() with async source resolution, off the event loop.

    1. Resolves any awaitable context values concurrently
    2. Drives kida's synchronous ``render_stream()`` on a dedicated worker
       thread, bridging each chunk back to the loop through a bounded queue so
       the loop is never blocked by CPU-bound chunk compilation
    3. Yields chunks as an async iterator for ASGI consumption while
       preserving progressive flush and chunk order

    See the module docstring for the threading + cancellation contract.

    Usage from negotiation.py::

        async for chunk in render_stream_async(kida_env, stream_value):
            await send_chunk(chunk)
    """
    # Phase 1: Resolve awaitables concurrently (on the loop).
    resolved_context = await resolve_stream_context(stream.context)

    template_name = stream.template_name

    # Bounded bridge between the worker thread and the loop. maxsize ==
    # _STREAM_CHUNK_BUFFER + 1 reserves one always-available slot for the
    # terminal sentinel so signalling end-of-stream never blocks; rendered
    # chunks are bounded to _STREAM_CHUNK_BUFFER + 1 in flight, applying
    # back-pressure (the worker blocks in `put` when the loop is slow) and
    # keeping memory bounded — preserving progressive flush.
    chunk_queue: queue.Queue[str | _StreamSentinel] = queue.Queue(maxsize=_STREAM_CHUNK_BUFFER + 1)

    # Worker -> loop signalling: the producer checks this on each iteration so a
    # consumer aclose()/disconnect stops the kida generator promptly even if the
    # next chunk is mid-compilation.
    stop_event = threading.Event()

    # Carries a render error from the worker thread back to the loop so the
    # consumer can re-raise it (preserving sender.py's mid-stream error path).
    error_box: list[BaseException] = []

    def _producer() -> None:
        """Drive kida's sync generator on the worker thread.

        Both the template fetch and the generator iteration happen here so all
        kida calls stay on a single thread (kida renderer contract). Each chunk
        is pushed to the loop via the bounded queue; ``put`` blocks the worker
        when the loop-side buffer is full (back-pressure).
        """
        sync_stream: Iterator[str] | None = None
        try:
            tmpl = env.get_template(template_name)
            sync_stream = tmpl.render_stream(resolved_context)
            for chunk in sync_stream:
                if stop_event.is_set():
                    break
                if chunk:
                    # Block until the consumer drains a slot or asks us to stop.
                    while not stop_event.is_set():
                        try:
                            chunk_queue.put(chunk, timeout=0.05)
                            break
                        except queue.Full:
                            continue
        except BaseException as exc:  # propagate render errors
            # A real render error (e.g. kida raised mid-stream). Stash it so the
            # consumer re-raises on the loop.
            error_box.append(exc)
        finally:
            # Close kida's generator on the SAME (worker) thread/context that
            # created it, so its render_context ContextVar resets cleanly.
            # (render_stream is annotated Iterator[str] but is a generator at
            # runtime, so close defensively.)
            close = getattr(sync_stream, "close", None)
            if close is not None:
                close()
            # Always signal end-of-stream (the reserved queue slot guarantees
            # this never blocks).
            chunk_queue.put(_STREAM_END)

    # Run the kida render on a dedicated worker thread, bridged to the loop via
    # a bounded queue. No anyio task group / portal wraps the `yield`, so a
    # consumer aclose() (GeneratorExit) unwinds cleanly instead of being wrapped
    # into a noisy ExceptionGroup. The shielded finally drives an orderly
    # shutdown and joins the thread, so it cannot leak.
    worker = threading.Thread(
        target=_producer,
        name="chirp-stream-render",
        daemon=True,
    )
    worker.start()
    try:
        while True:
            # Pull the next chunk off the loop via a worker thread so the queue
            # wait never blocks the event loop — this await lets concurrent loop
            # tasks make progress while the render thread computes.
            item = await anyio.to_thread.run_sync(chunk_queue.get)
            if isinstance(item, _StreamSentinel):
                break
            yield item
    finally:
        # Disconnect / early aclose / normal-end cleanup. Shielded so it always
        # runs even while unwinding a cancellation/GeneratorExit: signal the
        # producer to stop, drain any buffered chunks so a worker blocked in
        # `put` unwinds, then join the thread so it cannot leak past the
        # generator's aclose().
        with anyio.CancelScope(shield=True):
            stop_event.set()
            while worker.is_alive():
                with contextlib.suppress(queue.Empty):
                    chunk_queue.get_nowait()
                await anyio.to_thread.run_sync(worker.join, 0.05)

    # Re-raise any render error captured on the worker thread (mid-stream
    # failure) so sender.py's error path still fires on the loop.
    if error_box:
        raise error_box[0]


def has_async_context(context: dict[str, Any]) -> bool:
    """Check if a Stream() context contains any awaitables.

    Used by negotiation.py to decide between sync and async rendering paths.
    """
    return any(inspect.isawaitable(v) for v in context.values())

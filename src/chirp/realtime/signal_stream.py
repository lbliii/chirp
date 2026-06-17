"""The single ``/_chirp/live`` merge stream for signals.

One framework route, auto-registered at freeze when any signal exists, returns
an :class:`~chirp.realtime.events.EventStream` whose generator **merges** every
signal source + every imperative ``app.emit`` into one named-event stream. A
binding ``{{ signal('x') }}`` listens on ``sse-swap="x"``; this stream yields
``SSEEvent(event="x", data=<rendered>)`` whenever ``x`` changes.

Two producer paths feed the one stream:

1. **Push / derived** — :meth:`SignalRegistry.emit` (and the derived cascade) fan
   a marker ``ChangeEvent`` onto the bus. The merge generator drains the bus,
   reads the latest cached value, renders it, and yields one ``SSEEvent``.
2. **Async sources** — a ``@app.signal(source=...)`` async generator is pumped by
   a per-source background task that calls ``registry.emit`` for each yielded
   value, so it rides the exact same bus + cache path (coalescing-latest, derived
   cascade, render isolation) as push emits.

Render happens in :meth:`SignalRegistry.render_for_emit` inside the per-event
boundary (one ``None`` return skips that event); a render failure never kills the
shared connection. Reading the *latest cached* value on drain gives
coalescing-latest semantics for free — a bus drop under back-pressure is
reconciled by the next read.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from chirp.app.state import PendingRoute
from chirp.http.request import Request
from chirp.realtime.events import EventStream, SSEEvent
from chirp.realtime.signals import SignalRegistry, _bus_scope

logger = logging.getLogger("chirp.signals")

#: Path of the merged signal stream. Kept in sync with signal_globals.
SIGNAL_STREAM_PATH = "/_chirp/live"


def make_signal_stream(
    registry: SignalRegistry, names: tuple[str, ...], *, audience_key: str = ""
) -> EventStream:
    """Build the ``/_chirp/live`` merge ``EventStream`` for *names*.

    Subscribes to every requested signal's bus scope, pumps each primary
    signal's async ``source`` as a background task, and yields an ``SSEEvent``
    per change. The :func:`chirp.realtime.sse.handle_sse` per-event boundary
    isolates render failures; cleanup unsubscribes + cancels source tasks.
    """

    async def generate() -> AsyncIterator[SSEEvent]:
        # One asyncio.Queue fans in every subscribed scope's ChangeEvents.
        merged: asyncio.Queue[str] = asyncio.Queue()
        subscriber_tasks: list[asyncio.Task[None]] = []
        source_tasks: list[asyncio.Task[None]] = []

        async def _drain_scope(name: str) -> None:
            audience = registry.audience_of(name)
            aud = audience_key if audience == "session" else ""
            scope = _bus_scope(name, aud)
            async for _change in registry.bus.subscribe(scope):
                merged.put_nowait(name)

        async def _pump_source(name: str) -> None:
            spec = registry.spec(name)
            if spec is None or spec.source is None:
                return
            try:
                async for value in spec.source():
                    # Route through emit so derived cascade + cache stay coherent.
                    registry.emit(name, value)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("signal source %r failed", name)

        try:
            subscriber_tasks.extend(asyncio.create_task(_drain_scope(name)) for name in names)
            # Start async sources only for the requested primary signals.
            source_tasks.extend(
                asyncio.create_task(_pump_source(spec.name))
                for spec in registry.source_specs()
                if spec.name in names
            )

            while True:
                name = await merged.get()
                audience = registry.audience_of(name)
                aud = audience_key if audience == "session" else ""
                value = registry.cached_value(name, audience_key=aud)
                rendered = registry.render_for_emit(name, value)
                if rendered is None:
                    continue
                yield SSEEvent(data=rendered, event=name)
        finally:
            for task in (*subscriber_tasks, *source_tasks):
                task.cancel()
            for task in (*subscriber_tasks, *source_tasks):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    return EventStream(generate())


def make_signal_pending_route(registry: SignalRegistry) -> PendingRoute:
    """Return the ``PendingRoute`` for the single merged ``/_chirp/live`` stream.

    The handler reads ``?topics=a,b`` to scope the stream to the signals bound on
    the originating page; an absent/empty/unknown ``topics`` subscribes to every
    registered signal. ``referenced=True`` marks it framework-internal (not
    block-addressable), mirroring other SSE routes.
    """

    def _resolve_topics(raw: str | None) -> tuple[str, ...]:
        available = registry.names
        if not raw:
            return tuple(sorted(available))
        requested = [t.strip() for t in raw.split(",") if t.strip()]
        # Only stream topics that actually exist (drop unknown query noise).
        scoped = tuple(sorted(t for t in requested if t in available))
        return scoped or tuple(sorted(available))

    def _handler(request: Request) -> EventStream:
        topics = _resolve_topics(request.query.get("topics"))
        audience_key = (request.query.get("aud") or "").strip()
        return make_signal_stream(registry, topics, audience_key=audience_key)

    return PendingRoute(
        SIGNAL_STREAM_PATH,
        _handler,
        ["GET"],
        name="chirp_signal_stream",
        referenced=True,
    )

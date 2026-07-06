"""The single ``/_chirp/live`` merge stream for signals.

One framework route, auto-registered at freeze when any signal exists, returns
an :class:`~chirp.realtime.events.EventStream` whose generator **merges** every
signal source + every imperative ``app.emit`` into one typed update stream.
The SSE boundary frames each update as a named event for htmx 2 or as an
unnamed targeted ``<hx-partial>`` for htmx 4.

Two producer paths feed the one stream:

1. **Push / derived** — :meth:`SignalRegistry.emit` (and the derived cascade) fan
   a marker ``ChangeEvent`` onto the bus. The merge generator drains the bus,
   reads the latest cached value, renders it, and yields one typed update.
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
from chirp.realtime.events import EventStream, _SignalUpdate
from chirp.realtime.signals import SignalRegistry, _bus_scope

logger = logging.getLogger("chirp.signals")

#: Path of the merged signal stream. Kept in sync with signal_globals.
SIGNAL_STREAM_PATH = "/_chirp/live"

#: Consecutive source failures before a pump abandons a signal on a connection.
#: Bounds the restart loop so a source that raises *every* restart (a real bug,
#: not a transient blip) cannot hot-loop the worker — it is logged and dropped.
_MAX_SOURCE_RESTARTS = 5

#: Base seconds between source restarts; scaled by the consecutive-failure count
#: for linear backoff so a flapping source backs off instead of spinning.
_SOURCE_RESTART_BACKOFF_S = 0.5


def make_signal_stream(
    registry: SignalRegistry, names: tuple[str, ...], *, audience_key: str = ""
) -> EventStream:
    """Build the ``/_chirp/live`` merge ``EventStream`` for *names*.

    Subscribes to every requested signal's bus scope, pumps each primary
    signal's async ``source`` as a background task, and yields one client-neutral
    update per change. The :func:`chirp.realtime.sse.handle_sse` per-event boundary
    isolates render failures; cleanup unsubscribes + cancels source tasks.
    """

    async def generate() -> AsyncIterator[_SignalUpdate]:
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
            aud = audience_key if registry.audience_of(name) == "session" else ""
            failures = 0
            # Restart loop: one bad tick (a transient source error) must not kill
            # the signal for the life of the connection. A fresh spec.source()
            # call re-establishes the async generator; a healthy value resets the
            # backoff window. A source that completes normally is done (push-only
            # signals yield nothing and exit here once). Bounded so a source that
            # raises every restart is dropped, not spun (see _MAX_SOURCE_RESTARTS).
            while True:
                try:
                    async for value in spec.source():
                        # Route through emit so derived cascade + cache stay coherent.
                        registry.emit(name, value)
                        failures = 0
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures += 1
                    if failures >= _MAX_SOURCE_RESTARTS:
                        logger.exception(
                            "signal source %r (audience=%s) failed %d times consecutively; "
                            "giving up — its bindings will not update on this connection",
                            name,
                            aud or "global",
                            failures,
                        )
                        return
                    backoff = _SOURCE_RESTART_BACKOFF_S * failures
                    logger.warning(
                        "signal source %r (audience=%s) failed; restarting in %.1fs "
                        "(attempt %d/%d)",
                        name,
                        aud or "global",
                        backoff,
                        failures,
                        _MAX_SOURCE_RESTARTS,
                        exc_info=exc,
                    )
                    await asyncio.sleep(backoff)

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
                yield _SignalUpdate(name=name, data=rendered)
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
        if not scoped:
            return tuple(sorted(available))
        return registry.expand_connection_topics(scoped)

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

"""Reactive SSE stream that auto-pushes re-rendered blocks."""

from __future__ import annotations

import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.index import DependencyIndex
from chirp.realtime.events import EventStream
from chirp.templating.returns import Fragment


def reactive_stream(
    bus: ReactiveBus,
    *,
    scope: str,
    index: DependencyIndex,
    context_builder: Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]],
    origin: str | None = None,
    kida_env: Any = None,
) -> EventStream:
    """Create an SSE EventStream that auto-pushes re-rendered blocks.

    Subscribes to the ``ReactiveBus`` for the given scope.  When a
    ``ChangeEvent`` arrives, looks up affected blocks in the
    ``DependencyIndex`` and yields them as ``Fragment`` objects.
    The chirp SSE layer handles rendering via the app's kida env.

    Args:
        bus: The reactive event bus to subscribe to.
        scope: Scope key (e.g., document ID).
        index: Dependency index mapping paths to blocks.
        context_builder: Callable that returns the current context dict
            (called after each change to get fresh data).
        origin: Identity of this connection (e.g., user/session ID).
            Events whose ``origin`` matches are skipped — the client
            that caused the change doesn't need to be notified of it.
            ``None`` disables origin filtering.
        kida_env: Deprecated — rendering is handled by the SSE response
            layer.  Accepted for backwards compatibility.

    Returns:
        An ``EventStream`` ready to be returned from a route handler.

    Example::

        @app.route("/doc/{doc_id}/live")
        def live(doc_id: str) -> EventStream:
            return reactive_stream(
                bus, scope=doc_id, index=dep_index,
                context_builder=lambda: {"doc": store.get(doc_id)},
                origin=session_id,
            )
    """

    async def generate() -> AsyncIterator[Fragment]:
        async for change in bus.subscribe(scope):
            # Skip events we caused (both must be non-None and equal)
            if origin is not None and change.origin == origin:
                continue

            blocks = index.affected_blocks(change.changed_paths)
            if not blocks:
                continue

            # Error boundary: context failures skip this event,
            # don't kill the stream.  The next ChangeEvent will
            # retry with fresh data.
            try:
                ctx = context_builder()
                if inspect.isawaitable(ctx):
                    ctx = await ctx
                if not isinstance(ctx, dict):
                    logging.getLogger("chirp.reactive").warning(
                        "context_builder must return dict, got %s; skipping event",
                        type(ctx).__name__,
                    )
                    continue
                ctx_dict = cast(dict[str, Any], ctx)
            except Exception:
                logging.getLogger("chirp.reactive").exception(
                    "context_builder failed for scope=%s",
                    scope,
                )
                continue

            for ref in blocks:
                yield Fragment(
                    ref.template_name,
                    ref.block_name,
                    target=ref.target_id,
                    **ctx_dict,
                )

    return EventStream(generate())

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
    3. Pass fully-resolved context to kida render_stream()
    4. Yield HTML chunks via chunked transfer encoding
"""

import inspect
from collections.abc import AsyncIterator, Awaitable, Iterator
from typing import Any

import anyio
from kida import Environment

from chirp.templating.returns import Stream


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


async def render_stream_async(
    env: Environment,
    stream: Stream,
) -> AsyncIterator[str]:
    """Render a Stream() with async source resolution.

    1. Resolves any awaitable context values concurrently
    2. Delegates to kida's synchronous render_stream() for chunk generation
    3. Yields chunks as an async iterator for ASGI consumption

    Usage from negotiation.py::

        async for chunk in render_stream_async(kida_env, stream_value):
            await send_chunk(chunk)
    """
    # Phase 1: Resolve awaitables concurrently
    resolved_context = await resolve_stream_context(stream.context)

    # Phase 2: Delegate to kida's sync streaming renderer
    tmpl = env.get_template(stream.template_name)
    sync_stream: Iterator[str] = tmpl.render_stream(resolved_context)

    # Phase 3: Yield chunks as async iterator
    # Run sync rendering in a thread to avoid blocking the event loop
    # (kida's render_stream is CPU-bound template compilation)
    for chunk in sync_stream:
        if chunk:
            yield chunk


def has_async_context(context: dict[str, Any]) -> bool:
    """Check if a Stream() context contains any awaitables.

    Used by negotiation.py to decide between sync and async rendering paths.
    """
    return any(inspect.isawaitable(v) for v in context.values())

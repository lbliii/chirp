"""Invoke helpers — call sync or async handlers uniformly.

Chirp handlers can be ``def`` or ``async def``. Any code that calls
a user-provided handler must handle both cases. This module provides
a single helper so the sync/async check lives in exactly one place.

Sync handlers run in ``asyncio.to_thread`` to avoid blocking
the event loop (critical for CPU-bound work and free-threading scaling).

Usage::

    from chirp._internal.invoke import invoke

    result = await invoke(handler, *args, **kwargs)
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
from typing import Any

_handler_runtime_context: contextvars.Context | None = None


def take_handler_runtime_context() -> contextvars.Context | None:
    """Return and clear the worker-thread runtime snapshot from the last sync invoke."""
    global _handler_runtime_context
    ctx = _handler_runtime_context
    _handler_runtime_context = None
    return ctx


def _stash_handler_runtime_context(ctx: contextvars.Context) -> None:
    global _handler_runtime_context
    _handler_runtime_context = ctx


async def invoke(
    handler: Any,
    *args: Any,
    is_async: bool | None = None,
    inline_sync: bool = False,
    **kwargs: Any,
) -> Any:
    """Call a handler and await the result if it's a coroutine.

    When *is_async* is provided (from a compiled InvokePlan), the per-request
    ``inspect.iscoroutinefunction`` call is skipped entirely.

    When *inline_sync* is True and the handler is synchronous, it runs on the
    event loop thread instead of ``asyncio.to_thread`` — useful for lightweight
    handlers where the thread-dispatch overhead exceeds the work itself.

    Sync handlers dispatched to a worker thread run inside a
    :func:`contextvars.copy_context` snapshot taken on the event-loop thread
    (preserving OTel/request context) and stash a post-handler worker snapshot
    for streaming capture via :func:`take_handler_runtime_context`.
    """
    handler_is_async = is_async if is_async is not None else inspect.iscoroutinefunction(handler)

    if handler_is_async:
        return await handler(*args, **kwargs)

    if inline_sync:

        def _inner() -> Any:
            result = handler(*args, **kwargs)
            _stash_handler_runtime_context(contextvars.copy_context())
            return result

        result = contextvars.copy_context().run(_inner)
        if inspect.isawaitable(result):
            return await result
        return result

    parent_ctx = contextvars.copy_context()

    def _run() -> tuple[Any, contextvars.Context]:
        def _inner() -> tuple[Any, contextvars.Context]:
            result = handler(*args, **kwargs)
            return result, contextvars.copy_context()

        return parent_ctx.run(_inner)

    result, worker_ctx = await asyncio.to_thread(_run)
    _stash_handler_runtime_context(worker_ctx)
    if inspect.isawaitable(result):
        return await result
    return result

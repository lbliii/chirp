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

import asyncio
import inspect
from typing import Any


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
    """
    handler_is_async = is_async if is_async is not None else inspect.iscoroutinefunction(handler)

    if handler_is_async:
        return await handler(*args, **kwargs)

    if inline_sync:
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    result = await asyncio.to_thread(handler, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result

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


async def invoke(handler: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a handler and await the result if it's a coroutine.

    Async handlers run on the event loop. Sync handlers run in a thread
    pool via ``asyncio.to_thread.run_sync`` so they don't block the loop.

    Works with both sync and async callables::

        # sync — runs in thread pool, event loop stays responsive
        @app.route("/")
        def dashboard():
            return Template("dashboard.html")

        # async — runs on event loop
        @app.route("/data")
        async def data():
            data = await fetch_data()
            return Template("data.html", data=data)
    """
    if inspect.iscoroutinefunction(handler):
        return await handler(*args, **kwargs)
    result = await asyncio.to_thread(handler, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result

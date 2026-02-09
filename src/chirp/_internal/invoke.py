"""Invoke helpers — call sync or async handlers uniformly.

Chirp handlers can be ``def`` or ``async def``. Any code that calls
a user-provided handler must handle both cases. This module provides
a single helper so the sync/async check lives in exactly one place.

Usage::

    from chirp._internal.invoke import invoke

    result = await invoke(handler, *args, **kwargs)
"""

import inspect
from typing import Any


async def invoke(handler: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a handler and await the result if it's a coroutine.

    Works with both sync and async callables::

        # sync — returns immediately, no await needed
        @login_required
        def dashboard():
            return Template("dashboard.html")

        # async — returns coroutine, awaited automatically
        @login_required
        async def dashboard():
            data = await fetch_data()
            return Template("dashboard.html", data=data)
    """
    result = handler(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result

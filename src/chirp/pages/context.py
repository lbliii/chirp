"""Context cascade for filesystem-based page routes.

Runs ``_context.py`` providers from root to deepest, merging results.
Child context overrides parent — like Bengal's cascade_snapshot but
for live server requests instead of static site builds.
"""

from __future__ import annotations

import inspect
from typing import Any

from chirp.pages.types import ContextProvider


async def build_cascade_context(
    providers: tuple[ContextProvider, ...],
    path_params: dict[str, str],
) -> dict[str, Any]:
    """Run context providers from root to leaf, merging results.

    Each provider's output is merged into the accumulated context.
    Later providers (deeper in the filesystem) override earlier ones.

    Args:
        providers: Context providers ordered from root (depth=0) to leaf.
        path_params: Extracted path parameters from the URL match.

    Returns:
        Merged context dictionary.
    """
    ctx: dict[str, Any] = {}
    for provider in providers:
        result = _call_provider(provider.func, path_params)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            ctx.update(result)
    return ctx


def _call_provider(
    func: Any,
    path_params: dict[str, str],
) -> Any:
    """Call a context provider, injecting matching path params.

    The provider function's signature determines which path params
    it receives::

        async def context(doc_id: str) -> dict:
            ...  # receives doc_id from /doc/{doc_id}/...

        def context() -> dict:
            ...  # receives nothing
    """
    sig = inspect.signature(func)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name in path_params:
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except (ValueError, TypeError):
                    kwargs[name] = value
            else:
                kwargs[name] = value

    return func(**kwargs)

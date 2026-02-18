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

    Providers may raise ``HTTPError`` subclasses (e.g. ``NotFound``)
    to abort the cascade early.  The exception propagates to the
    caller (``page_wrapper``), which is wrapped by ``handle_request``
    — chirp's standard error pipeline renders the appropriate error
    page automatically.  This eliminates the need for downstream
    handlers to guard against missing resources::

        # In _context.py:
        from chirp import NotFound

        def context(doc_id: str) -> dict:
            doc = store.get(doc_id)
            if doc is None:
                raise NotFound(f"Document {doc_id} not found")
            return {"doc": doc}

    Args:
        providers: Context providers ordered from root (depth=0) to leaf.
        path_params: Extracted path parameters from the URL match.

    Returns:
        Merged context dictionary.

    Raises:
        HTTPError: If a provider raises (e.g. ``NotFound``).
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
    sig = inspect.signature(func, eval_str=True)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name in path_params:
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except ValueError, TypeError:
                    kwargs[name] = value
            else:
                kwargs[name] = value

    return func(**kwargs)

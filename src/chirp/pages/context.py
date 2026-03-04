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
    service_providers: dict[type, Any] | None = None,
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
        service_providers: Type-keyed factories from ``app.provide()``.
            Provider params with matching annotations are resolved from these.

    Returns:
        Merged context dictionary.

    Raises:
        HTTPError: If a provider raises (e.g. ``NotFound``).
    """
    ctx: dict[str, Any] = {}
    svc = service_providers or {}
    for provider in providers:
        result = _call_provider(provider.func, path_params, ctx, svc)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            ctx.update(result)
    return ctx


def _call_provider(
    func: Any,
    path_params: dict[str, str],
    accumulated_ctx: dict[str, Any],
    service_providers: dict[type, Any],
) -> Any:
    """Call a context provider, injecting path params, parent context, and services.

    The provider function's signature determines which arguments it receives:
    - Path params (e.g. ``name`` from ``/skill/{name}``) come from the URL.
    - Other params come from the accumulated context of parent providers.
    - Params with type annotations matching ``app.provide()`` are resolved
      from service providers::

        def context() -> dict:
            ...  # receives nothing

        def context(doc_id: str, store: DocumentStore) -> dict:
            ...  # doc_id from path, store from app.provide()
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
        elif name in accumulated_ctx:
            kwargs[name] = accumulated_ctx[name]
        elif (
            param.annotation is not inspect.Parameter.empty
            and param.annotation in service_providers
        ):
            kwargs[name] = service_providers[param.annotation]()

    return func(**kwargs)

"""Page handler argument resolution and result upgrade.

Extracts the parameter-resolution and Page-to-LayoutPage logic from
the ``page_wrapper`` closure in ``App._register_page_handler`` into
standalone, testable functions.

Resolution priority for each handler parameter:

1. ``request`` — the Request object (by name or annotation)
2. Path parameters — from the URL match, with type coercion
3. Cascade context — from ``_context.py`` providers
4. Service providers — registered via ``app.provide()``
5. Extractable dataclasses — from query (GET) or body (POST)
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from chirp.extraction import extract_dataclass, is_extractable_dataclass

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.pages.types import ContextProvider, LayoutChain


async def resolve_kwargs(
    handler: Callable[..., Any],
    request: Request,
    cascade_ctx: dict[str, Any],
    service_providers: dict[type, Callable[..., Any]],
) -> dict[str, Any]:
    """Build keyword arguments for a page handler from request context.

    Inspects *handler*'s signature and resolves each parameter from the
    available sources in priority order.  For non-GET methods, pre-reads
    the request body when the handler expects an extractable dataclass.

    Args:
        handler: The user-defined page handler function.
        request: The current HTTP request.
        cascade_ctx: Merged context from ``_context.py`` providers.
        service_providers: Type-keyed factories from ``app.provide()``.

    Returns:
        A dict of keyword arguments ready to pass to *handler*.
    """
    from chirp.http.request import Request as RequestType

    # Pre-read body for typed extraction (non-GET only)
    body_data: dict[str, Any] | None = None
    if request.method not in ("GET", "HEAD"):
        sig_check = inspect.signature(handler, eval_str=True)
        needs_body = any(
            p.annotation is not inspect.Parameter.empty and is_extractable_dataclass(p.annotation)
            for p in sig_check.parameters.values()
        )
        if needs_body:
            ct = request.content_type or ""
            if "json" in ct:
                body_data = await request.json()
            else:
                body_data = dict(await request.form())

    # Build kwargs from handler signature
    sig = inspect.signature(handler, eval_str=True)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name == "request" or param.annotation is RequestType:
            kwargs[name] = request
        elif name in request.path_params:
            value = request.path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except ValueError, TypeError:
                    kwargs[name] = value
            else:
                kwargs[name] = value
        elif name in cascade_ctx:
            kwargs[name] = cascade_ctx[name]
        elif (
            param.annotation is not inspect.Parameter.empty
            and param.annotation in service_providers
        ):
            kwargs[name] = service_providers[param.annotation]()
        elif param.annotation is not inspect.Parameter.empty and is_extractable_dataclass(
            param.annotation
        ):
            if request.method in ("GET", "HEAD"):
                kwargs[name] = extract_dataclass(
                    param.annotation,
                    request.query,
                )
            elif body_data is not None:
                kwargs[name] = extract_dataclass(
                    param.annotation,
                    body_data,
                )

    return kwargs


def upgrade_result(
    result: Any,
    cascade_ctx: dict[str, Any],
    layout_chain: LayoutChain | None,
    context_providers: tuple[ContextProvider, ...],
) -> Any:
    """Upgrade a Page result to a LayoutPage with layout chain metadata.

    If *result* is a ``Page``, merges cascade context with the page's
    own context and wraps it in a ``LayoutPage`` for layout composition.
    All other return types pass through unchanged.

    Args:
        result: The handler's return value.
        cascade_ctx: Merged context from ``_context.py`` providers.
        layout_chain: The layout chain for this page route.
        context_providers: The context providers for this page route.

    Returns:
        A ``LayoutPage`` if *result* was a ``Page``, otherwise *result*
        unchanged.
    """
    from chirp.templating.returns import LayoutPage, Page

    if isinstance(result, Page):
        merged_ctx = {**cascade_ctx, **result.context}
        return LayoutPage(
            result.name,
            result.block_name,
            layout_chain=layout_chain,
            context_providers=context_providers,
            **merged_ctx,
        )

    return result

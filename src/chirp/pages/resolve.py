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
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from chirp.extraction import extract_dataclass, is_extractable_dataclass
from chirp.pages.shell_actions import (
    SHELL_ACTIONS_CONTEXT_KEY,
    merge_shell_actions,
    normalize_shell_actions,
)


def _invoke_provider_factory(
    factory: Callable[..., Any],
    request: Request,
    cascade_ctx: dict[str, Any],
) -> Any:
    """Call a service provider factory, injecting request/cascade_ctx if requested."""
    from chirp.http.request import Request as RequestType

    sig = inspect.signature(factory, eval_str=True)
    kwargs: dict[str, Any] = {}
    for pname, p in sig.parameters.items():
        if pname == "request" or p.annotation is RequestType:
            kwargs[pname] = request
        elif pname in ("cascade_ctx", "context"):
            kwargs[pname] = cascade_ctx
    return factory(**kwargs)


if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.pages.types import ContextProvider, LayoutChain


def _warn_if_page_root_missing(result: Any) -> None:
    """Warn about common mounted-pages fragment roots that drop page wrappers."""
    from chirp.templating.returns import Page

    if not isinstance(result, Page):
        return
    if result.page_block_name is not None:
        return
    if result.block_name != "page_content":
        return
    warnings.warn(
        "Page(..., 'page_content') inside mount_pages should set "
        "page_block_name='page_root' (or another fragment-safe page root) "
        "so boosted navigation preserves page-level wrappers.",
        UserWarning,
        stacklevel=3,
    )


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
            factory = service_providers[param.annotation]
            kwargs[name] = _invoke_provider_factory(factory, request, cascade_ctx)
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
    request: Request | None = None,
) -> Any:
    """Upgrade a Page result to a LayoutPage with layout chain metadata.

    If *result* is a ``Page``, merges cascade context with the page's
    own context and wraps it in a ``LayoutPage`` for layout composition.
    If *result* is a ``Suspense`` and *layout_chain* has layouts, wraps
    it in a ``LayoutSuspense`` so the shell is composed with layouts.
    All other return types pass through unchanged.

    Args:
        result: The handler's return value.
        cascade_ctx: Merged context from ``_context.py`` providers.
        layout_chain: The layout chain for this page route.
        context_providers: The context providers for this page route.
        request: The current request (for LayoutSuspense fragment detection).

    Returns:
        A ``LayoutPage`` if *result* was a ``Page``, a ``LayoutSuspense``
        if *result* was a ``Suspense`` with layouts, otherwise *result*
        unchanged.
    """
    from chirp.templating.composition import PageComposition
    from chirp.templating.returns import OOB, LayoutPage, LayoutSuspense, Page, Suspense

    merged_ctx = _merge_result_context(cascade_ctx, getattr(result, "context", {}))

    if isinstance(result, Page):
        _warn_if_page_root_missing(result)
        return LayoutPage(
            result.name,
            result.block_name,
            page_block_name=result.page_block_name,
            layout_chain=layout_chain,
            context_providers=context_providers,
            **merged_ctx,
        )

    if (
        isinstance(result, Suspense)
        and layout_chain is not None
        and getattr(layout_chain, "layouts", ())
    ):
        layout_ctx = {k: (None if inspect.isawaitable(v) else v) for k, v in merged_ctx.items()}
        return LayoutSuspense(
            result,
            layout_chain,
            context=layout_ctx,
            request=request,
        )

    if isinstance(result, OOB):
        upgraded_main = upgrade_result(
            result.main,
            cascade_ctx,
            layout_chain,
            context_providers,
            request=request,
        )
        if upgraded_main is result.main:
            return result
        return OOB(upgraded_main, *result.oob_fragments)

    if isinstance(result, PageComposition):
        needs_chain = result.layout_chain is None and layout_chain is not None
        needs_providers = not result.context_providers and context_providers
        if needs_chain or needs_providers:
            merged_ctx = _merge_result_context(cascade_ctx, result.context)
            return PageComposition(
                template=result.template,
                fragment_block=result.fragment_block,
                page_block=result.page_block,
                context=merged_ctx,
                regions=result.regions,
                layout_chain=layout_chain if needs_chain else result.layout_chain,
                context_providers=context_providers if needs_providers else result.context_providers,
            )
        return result

    return result


def _merge_result_context(
    cascade_ctx: dict[str, Any], result_ctx: dict[str, Any]
) -> dict[str, Any]:
    """Merge page result context with cascade context, preserving shell semantics."""
    merged_ctx = {**cascade_ctx, **result_ctx}
    cascade_actions = normalize_shell_actions(cascade_ctx.get(SHELL_ACTIONS_CONTEXT_KEY))
    result_actions = normalize_shell_actions(result_ctx.get(SHELL_ACTIONS_CONTEXT_KEY))
    merged_actions = merge_shell_actions(cascade_actions, result_actions)
    if merged_actions is not None:
        merged_ctx[SHELL_ACTIONS_CONTEXT_KEY] = merged_actions
    return merged_ctx

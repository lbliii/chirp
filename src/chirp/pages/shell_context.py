"""Shell context assembly from RouteMeta and section.

Builds page_title, breadcrumb_items, tab_items, current_path for
layout templates. Only includes keys where source is non-None.
"""

from __future__ import annotations

import inspect
from typing import Any

from chirp.http.request import Request
from chirp.pages.types import RouteMeta


async def resolve_meta(
    meta: RouteMeta | None,
    meta_provider: Any,
    path_params: dict[str, str],
    service_providers: dict[type, Any],
) -> RouteMeta | None:
    """Resolve RouteMeta from static meta or meta_provider callable.

    Supports both sync and async meta() providers. Uses same arg
    resolution as _call_provider: path params, empty accumulated
    context, and service providers.

    Returns:
        Static meta, or result of meta_provider(), or None if both absent.
    """
    if meta is not None:
        return meta
    if meta_provider is None or not callable(meta_provider):
        return None

    result = _call_meta_provider(meta_provider, path_params, {}, service_providers)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, RouteMeta):
        return result
    if isinstance(result, dict):
        return _dict_to_route_meta(result)
    return None


def _dict_to_route_meta(d: dict[str, Any]) -> RouteMeta:
    """Convert a dict returned by a meta provider to RouteMeta."""
    return RouteMeta(
        title=d.get("title"),
        section=d.get("section"),
        breadcrumb_label=d.get("breadcrumb_label"),
        shell_mode=d.get("shell_mode"),
        auth=d.get("auth"),
        cache=d.get("cache"),
        tags=tuple(d.get("tags", ())) if isinstance(d.get("tags"), (list, tuple)) else (),
    )


def _call_meta_provider(
    func: Any,
    path_params: dict[str, str],
    accumulated_ctx: dict[str, Any],
    service_providers: dict[type, Any],
) -> Any:
    """Call meta provider with path params, context, and services."""
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


def build_shell_context(
    request: Request,
    meta: RouteMeta | None,
    section_ctx: dict[str, Any],
    cascade_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Build shell context from request, meta, and section.

    Produces:
        - current_path from request.path
        - page_title from meta.title
        - breadcrumb_items from section prefix + meta.breadcrumb_label
        - tab_items from section tab items

    Only includes keys where source is non-None.
    """
    result: dict[str, Any] = {}

    # current_path always available from request
    result["current_path"] = request.path

    if meta is not None and meta.title is not None:
        result["page_title"] = meta.title

    # breadcrumb_items: section prefix + optional meta.breadcrumb_label
    # Also expose breadcrumb_prefix and breadcrumb_label for OOB blocks
    # that render in isolation (they need to build items from context).
    breadcrumb_prefix = section_ctx.get("breadcrumb_prefix") or []
    breadcrumb_label = meta.breadcrumb_label if meta else None
    if breadcrumb_prefix or breadcrumb_label is not None:
        result["breadcrumb_prefix"] = breadcrumb_prefix
        if breadcrumb_label is not None:
            result["breadcrumb_label"] = breadcrumb_label
    breadcrumb_parts: list[dict[str, str]] = list(breadcrumb_prefix)
    if breadcrumb_label is not None:
        breadcrumb_parts.append({"label": breadcrumb_label, "href": request.path})
    if breadcrumb_parts:
        result["breadcrumb_items"] = breadcrumb_parts

    if section_ctx.get("tab_items"):
        result["tab_items"] = section_ctx["tab_items"]

    return result

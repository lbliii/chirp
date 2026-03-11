"""Route contract debug metadata for LayoutDebugMiddleware.

When config.debug is True, page handlers store route contract info on the
request. LayoutDebugMiddleware reads it and emits X-Chirp-Route-* headers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from chirp.http.request import Request

_CACHE_KEY = "_route_debug"


@dataclass(frozen=True, slots=True)
class RouteDebugInfo:
    """Route contract metadata for debug headers."""

    route_kind: str
    route_files: str
    route_meta: str
    route_section: str
    context_chain: str
    shell_context_keys: str


def set_route_debug_metadata(request: Request | None, info: RouteDebugInfo) -> None:
    """Store route debug metadata on the request for LayoutDebugMiddleware."""
    if request is not None:
        request._cache[_CACHE_KEY] = info


def get_route_debug_metadata(request: Request | None) -> RouteDebugInfo | None:
    """Retrieve route debug metadata from the request (does not pop)."""
    if request is None:
        return None
    return request._cache.get(_CACHE_KEY)


def build_route_debug_info(
    *,
    route_kind: str,
    template_name: str | None,
    meta: object | None,
    meta_provider: object | None,
    context_providers: tuple[object, ...],
    layout_chain: object,
    actions: tuple[object, ...],
    viewmodel_provider: object | None,
    meta_resolved: object | None,
    section_ctx: dict,
    shell_ctx: dict,
) -> RouteDebugInfo:
    """Build RouteDebugInfo from page_wrapper context."""
    files: list[str] = []
    files.append("page.py")
    if template_name:
        files.append(template_name.split("/")[-1] if "/" in template_name else template_name)
    if meta is not None or meta_provider is not None:
        files.append("_meta.py")
    for p in context_providers:
        depth = getattr(p, "depth", 0)
        mod_path = getattr(p, "module_path", "")
        if mod_path:
            path = Path(mod_path)
            short = f"{path.parent.name}/_context.py({depth})" if path.parent.name else f"_context.py({depth})"
        else:
            short = f"_context.py({depth})"
        files.append(short)
    for lay in getattr(layout_chain, "layouts", ()):
        tpl = getattr(lay, "template_name", "")
        if tpl and "_layout" in tpl:
            files.append(tpl.split("/")[-1] if "/" in tpl else tpl)
    if actions:
        files.append("_actions.py")
    if viewmodel_provider is not None:
        files.append("_viewmodel.py")

    route_files = ", ".join(files)

    meta_dict: dict[str, str | None] = {}
    if meta_resolved is not None:
        meta_dict = {
            "title": getattr(meta_resolved, "title", None),
            "section": getattr(meta_resolved, "section", None),
            "breadcrumb_label": getattr(meta_resolved, "breadcrumb_label", None),
            "shell_mode": getattr(meta_resolved, "shell_mode", None),
        }
    route_meta = json.dumps({k: v for k, v in meta_dict.items() if v is not None})

    route_section = (
        getattr(meta_resolved, "section", None) if meta_resolved else None
    ) or "none"

    chain_parts: list[str] = []
    for p in context_providers:
        depth = getattr(p, "depth", 0)
        mod_path = getattr(p, "module_path", "")
        if mod_path:
            path = Path(mod_path)
            short = f"{path.parent.name}/_context.py" if path.parent.name else "_context.py"
        else:
            short = "_context.py"
        chain_parts.append(f"{short}({depth})")
    context_chain = " > ".join(chain_parts) if chain_parts else ""

    shell_keys = ", ".join(sorted(shell_ctx.keys())) if shell_ctx else ""

    return RouteDebugInfo(
        route_kind=route_kind,
        route_files=route_files,
        route_meta=route_meta,
        route_section=route_section,
        context_chain=context_chain,
        shell_context_keys=shell_keys,
    )

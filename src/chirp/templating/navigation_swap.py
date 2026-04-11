"""Route-aware boosted navigation swap resolution (hierarchical shell scopes).

Pure helpers map (current path, destination path, layout chains) to a
recommended ``hx-target`` and symbolic scope name. Server rendering still
uses ``HX-Target`` and :class:`FragmentTargetRegistry` at runtime; this module
only helps authors avoid hand-authoring targets on every link.
"""

from __future__ import annotations

import logging
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SwapResolution:
    """Recommended swap for a boosted GET navigation."""

    htmx_target: str
    """Value for ``hx-target`` (includes ``#`` prefix)."""

    scope: str
    """Symbolic scope name or concrete target id."""

    fragment_block: str | None
    """Block name from the fragment registry when registered."""


def normalize_route_path(path: str) -> str:
    """Normalize a URL path for comparisons (no query or fragment)."""
    if not path:
        return "/"
    p = path.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if not p.startswith("/"):
        p = "/" + p
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


def resolve_destination_path(current_path: str, href: str) -> str | None:
    """Resolve *href* to an absolute site path, or None if external / unusable."""
    href = href.strip()
    if not href or href.startswith("#"):
        return normalize_route_path(current_path)
    if href.startswith(("http://", "https://")):
        return None
    if href.startswith("//"):
        return None
    if href.startswith("/"):
        return normalize_route_path(href)
    cur = normalize_route_path(current_path)
    if cur == "/":
        base = "/"
    else:
        parent = posixpath.dirname(cur)
        base = parent if parent == "/" else parent + "/"
    joined = posixpath.normpath(base + href)
    if not joined.startswith("/"):
        joined = "/" + joined
    return normalize_route_path(joined)


def common_layout_prefix_len(a: LayoutChain, b: LayoutChain) -> int:
    """Length of the longest common prefix of two layout chains (template-wise)."""
    la, lb = a.layouts, b.layouts
    if not la or not lb:
        return 0
    n = min(len(la), len(lb))
    count = 0
    for i in range(n):
        if la[i] != lb[i]:
            break
        count += 1
    return count


def pick_outlet_layout_index(*, nc: int, nd: int, common: int) -> int:
    """Choose which layout level owns the primary outlet for this transition."""
    if nc == nd == common and nc > 0:
        return nc - 1
    if common == 0:
        return 0
    return common - 1


def concrete_target_id(layout: LayoutInfo, swap_scope_map: Mapping[str, str]) -> str:
    """Resolve DOM target id (no #) for a layout using scope map and metadata."""
    if layout.swap_scope_name:
        mapped = swap_scope_map.get(layout.swap_scope_name)
        if mapped:
            return mapped.lstrip("#")
    if layout.outlet_target_id:
        return layout.outlet_target_id.lstrip("#")
    return layout.target


def _scope_label(
    layout: LayoutInfo,
    target_id: str,
    swap_scope_map: Mapping[str, str],
) -> str:
    if layout.swap_scope_name:
        return layout.swap_scope_name
    for name, tid in swap_scope_map.items():
        if tid.lstrip("#") == target_id:
            return name
    return target_id


def resolve_navigation_swap(
    *,
    current_path: str,
    destination_path: str,
    layout_chain_current: LayoutChain | None,
    layout_chain_dest: LayoutChain | None,
    registry: FragmentTargetRegistry,
    swap_scope_map: Mapping[str, str],
) -> SwapResolution | None:
    """Return recommended swap metadata for boosted navigation, or None.

    *destination_path* must be normalized (see :func:`normalize_route_path`).
    When the destination has no layout chain, returns None. When current and
    destination paths are equal, returns None (avoid redundant swaps).
    """
    cur = normalize_route_path(current_path)
    dest = normalize_route_path(destination_path)
    if cur == dest:
        return None
    if layout_chain_dest is None or not layout_chain_dest.layouts:
        return None

    layouts_dest = layout_chain_dest.layouts
    nd = len(layouts_dest)

    layouts_curr = layout_chain_current.layouts if layout_chain_current else ()
    nc = len(layouts_curr)

    common = (
        common_layout_prefix_len(layout_chain_current, layout_chain_dest)
        if layout_chain_current and layouts_curr
        else 0
    )

    idx = pick_outlet_layout_index(nc=nc, nd=nd, common=common)
    if idx < 0 or idx >= nd:
        idx = max(0, nd - 1)

    layout = layouts_dest[idx]
    tid = concrete_target_id(layout, swap_scope_map)
    scope = _scope_label(layout, tid, swap_scope_map)

    cfg = registry.get(tid)
    if cfg is None:
        _logger.debug(
            "navigation_swap: target %r not registered in fragment registry",
            tid,
        )

    return SwapResolution(
        htmx_target=f"#{tid}",
        scope=scope,
        fragment_block=cfg.fragment_block if cfg is not None else None,
    )


def make_swap_attrs(
    *,
    route_layout_chains: Mapping[str, Any],
    router: Any | None,
    fragment_target_registry: FragmentTargetRegistry,
    swap_scope_map: Mapping[str, str],
) -> Any:
    """Build the template global ``swap_attrs(href, *, hx_boost=True)``."""

    def swap_attrs(href: str, *, hx_boost: bool = True) -> dict[str, str]:
        from chirp.context import get_request
        from chirp.errors import MethodNotAllowed, NotFound

        try:
            request = get_request()
        except LookupError:
            return {}
        current = normalize_route_path(request.path)
        dest = resolve_destination_path(current, href)
        if dest is None:
            _logger.debug("navigation_swap: external or unresolved href %r", href)
            return {}

        layout_current: LayoutChain | None = None
        layout_dest: LayoutChain | None = None
        if router is None:
            return {}
        try:
            m = router.match("GET", dest)
            layout_dest = route_layout_chains.get(m.route.path)
        except NotFound, MethodNotAllowed:
            _logger.debug("navigation_swap: no route for destination %r", dest)
            return {}
        try:
            mc = router.match("GET", current)
            layout_current = route_layout_chains.get(mc.route.path)
        except NotFound, MethodNotAllowed:
            layout_current = None

        res = resolve_navigation_swap(
            current_path=current,
            destination_path=dest,
            layout_chain_current=layout_current,
            layout_chain_dest=layout_dest,
            registry=fragment_target_registry,
            swap_scope_map=swap_scope_map,
        )
        if res is None:
            return {}
        out: dict[str, str] = {"hx-target": res.htmx_target}
        if hx_boost:
            out["hx-boost"] = "true"
        return out

    return swap_attrs

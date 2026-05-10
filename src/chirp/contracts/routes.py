"""Route helpers for contracts checker."""

import re
from urllib.parse import unquote

from chirp.routing.params import CONVERTERS
from chirp.routing.router import Router, parse_path


def _normalize_path(path: str) -> str:
    """Normalize path for lookup (strip slashes, empty becomes '')."""
    return path.strip("/") or ""


def attr_to_method(attr: str, method_override: str | None = None) -> str:
    """Map a URL-bearing template attribute name to HTTP method."""
    if attr == "action":
        return method_override if method_override in ("GET", "POST") else "GET"
    if attr == "confirm_url":
        return method_override if method_override else "POST"
    return attr.split("-", 1)[1].upper()


def collect_route_paths(router: Router) -> dict[str, frozenset[str]]:
    """Map route path to allowed methods."""
    path_methods: dict[str, set[str]] = {}
    for route in router.routes:
        if route.path not in path_methods:
            path_methods[route.path] = set()
        path_methods[route.path].update(route.methods)
    return {path: frozenset(methods) for path, methods in path_methods.items()}


def path_matches_route(url: str, route_path: str) -> bool:
    """Check if URL could match a route pattern."""
    path_only = url.split("?")[0] if "?" in url else url
    url_parts = [part for part in path_only.strip("/").split("/") if part]
    route_segments = parse_path(route_path)

    if not route_segments:
        return not url_parts

    has_path_converter = route_segments[-1].is_param and route_segments[-1].param_type == "path"
    if has_path_converter:
        if len(url_parts) < len(route_segments):
            return False
    elif len(url_parts) != len(route_segments):
        return False

    for index, route_seg in enumerate(route_segments):
        if route_seg.is_param and route_seg.param_type == "path":
            remaining = "/".join(url_parts[index:])
            pattern, _ = CONVERTERS["path"]
            return re.fullmatch(pattern, unquote(remaining)) is not None

        url_seg = url_parts[index]
        if route_seg.is_param:
            pattern, _ = CONVERTERS[route_seg.param_type]
            value = unquote(url_seg) if route_seg.param_type != "str" else url_seg
            if re.fullmatch(pattern, value) is None:
                return False
            continue
        if url_seg != route_seg.value:
            return False
    return True


def build_route_index(
    route_paths: dict[str, frozenset[str]],
) -> tuple[dict[str, tuple[str, frozenset[str]]], list[tuple[str, frozenset[str]]]]:
    """Pre-segment routes for O(1) static and O(parametric) URL matching.

    Returns (static_routes, parametric_routes). For static URLs use dict lookup;
    for parametric URLs scan only parametric_routes.
    """
    static_routes: dict[str, tuple[str, frozenset[str]]] = {}
    parametric_routes: list[tuple[str, frozenset[str]]] = []
    for path, methods in route_paths.items():
        entry = (path, methods)
        if "{" in path:
            parametric_routes.append(entry)
        else:
            static_routes[_normalize_path(path)] = entry
    return static_routes, parametric_routes


def find_matching_route(
    url: str,
    static_routes: dict[str, tuple[str, frozenset[str]]],
    parametric_routes: list[tuple[str, frozenset[str]]],
) -> tuple[str, frozenset[str]] | None:
    """Find route matching URL. O(1) for static, O(parametric) for parametric."""
    path_only = url.split("?")[0] if "?" in url else url
    normalized = _normalize_path(path_only)
    if normalized in static_routes:
        return static_routes[normalized]
    for route_path, methods in parametric_routes:
        if path_matches_route(url, route_path):
            return (route_path, methods)
    return None

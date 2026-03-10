"""Route helpers for contracts checker."""

from chirp.routing.router import Router


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
    url_parts = path_only.strip("/").split("/")
    route_parts = route_path.strip("/").split("/")
    if len(url_parts) != len(route_parts):
        if route_parts and route_parts[-1].startswith("{") and ":path" in route_parts[-1]:
            return len(url_parts) >= len(route_parts) - 1
        return False
    for url_seg, route_seg in zip(url_parts, route_parts, strict=True):
        if route_seg.startswith("{") and route_seg.endswith("}"):
            continue
        if url_seg != route_seg:
            return False
    return True

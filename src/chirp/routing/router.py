"""Compiled router with trie-based path matching.

Routes are registered during setup and compiled into an immutable
lookup structure when the app freezes.
"""

import re
from dataclasses import dataclass

from chirp.errors import MethodNotAllowed, NotFound
from chirp.routing.params import CONVERTERS
from chirp.routing.route import PathSegment, Route, RouteMatch


def parse_path(path: str) -> list[PathSegment]:
    """Parse a route path string into segments.

    Examples::

        "/users"          -> [PathSegment("users")]
        "/users/{id}"     -> [PathSegment("users"), PathSegment("{id}", is_param=True, ...)]
        "/users/{id:int}" -> [PathSegment("{id:int}", is_param=True, param_type="int")]
        "/files/{path:path}" -> [PathSegment("{path:path}", is_param=True, param_type="path")]
    """
    segments: list[PathSegment] = []
    for part in path.strip("/").split("/"):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            inner = part[1:-1]
            if ":" in inner:
                param_name, param_type = inner.split(":", 1)
            else:
                param_name = inner
                param_type = "str"
            segments.append(
                PathSegment(
                    value=part,
                    is_param=True,
                    param_name=param_name,
                    param_type=param_type,
                )
            )
        else:
            segments.append(PathSegment(value=part))
    return segments


class _TrieNode:
    """A node in the route trie. Mutable during compilation only."""

    __slots__ = ("catch_all_route", "children", "param_child", "routes_by_method")

    def __init__(self) -> None:
        # Static segment children: "users" -> node
        self.children: dict[str, _TrieNode] = {}
        # Single parameter child (only one param pattern per level)
        self.param_child: _ParamEdge | None = None
        # Catch-all route (path converter)
        self.catch_all_route: _CatchAllEdge | None = None
        # Routes at this node, keyed by HTTP method
        self.routes_by_method: dict[str, Route] = {}


@dataclass(slots=True)
class _ParamEdge:
    """A parameter edge in the trie."""

    param_name: str
    param_type: str
    regex: re.Pattern[str]
    node: _TrieNode


@dataclass(slots=True)
class _CatchAllEdge:
    """A catch-all (path) edge — consumes remaining path."""

    param_name: str
    route_by_method: dict[str, Route]


class Router:
    """Compiled router with trie-based path matching.

    Usage::

        router = Router()
        router.add(Route("/users", handler, frozenset({"GET"})))
        router.add(Route("/users/{id:int}", handler, frozenset({"GET"})))
        router.compile()
        match = router.match("GET", "/users/42")
    """

    __slots__ = ("_compiled", "_root")

    def __init__(self) -> None:
        self._root = _TrieNode()
        self._compiled = False

    def add(self, route: Route) -> None:
        """Add a route to the router. Must be called before compile()."""
        if self._compiled:
            msg = "Cannot add routes after compilation."
            raise RuntimeError(msg)

        segments = parse_path(route.path)
        node = self._root

        for _i, seg in enumerate(segments):
            if seg.is_param and seg.param_type == "path":
                # Catch-all: consumes rest of path, must be last segment
                if node.catch_all_route is None:
                    node.catch_all_route = _CatchAllEdge(
                        param_name=seg.param_name or "path",
                        route_by_method={},
                    )
                for method in route.methods:
                    node.catch_all_route.route_by_method[method] = route
                return

            if seg.is_param:
                # Parameter segment
                if node.param_child is None:
                    pattern, _ = CONVERTERS[seg.param_type]
                    node.param_child = _ParamEdge(
                        param_name=seg.param_name or "",
                        param_type=seg.param_type,
                        regex=re.compile(f"^{pattern}$"),
                        node=_TrieNode(),
                    )
                node = node.param_child.node
            else:
                # Static segment
                if seg.value not in node.children:
                    node.children[seg.value] = _TrieNode()
                node = node.children[seg.value]

        # Register methods at the terminal node
        for method in route.methods:
            node.routes_by_method[method] = route

    @property
    def routes(self) -> list[Route]:
        """Return all registered routes.

        Traverses the trie to collect every unique Route object.
        Useful for introspection and contract validation.

        """
        seen: set[int] = set()
        result: list[Route] = []
        self._collect_routes(self._root, seen, result)
        return result

    def _collect_routes(
        self,
        node: _TrieNode,
        seen: set[int],
        result: list[Route],
    ) -> None:
        """Recursively collect routes from the trie."""
        for route in node.routes_by_method.values():
            route_id = id(route)
            if route_id not in seen:
                seen.add(route_id)
                result.append(route)

        for child in node.children.values():
            self._collect_routes(child, seen, result)

        if node.param_child is not None:
            self._collect_routes(node.param_child.node, seen, result)

        if node.catch_all_route is not None:
            for route in node.catch_all_route.route_by_method.values():
                route_id = id(route)
                if route_id not in seen:
                    seen.add(route_id)
                    result.append(route)

    def compile(self) -> None:
        """Freeze the router. No more routes can be added."""
        self._compiled = True

    def match(self, method: str, path: str) -> RouteMatch:
        """Match a request path and method against compiled routes.

        Returns a ``RouteMatch`` on success.
        Raises ``NotFound`` if no route matches the path.
        Raises ``MethodNotAllowed`` if the path matches but the method doesn't.
        """
        parts = [p for p in path.strip("/").split("/") if p]
        result = self._match_node(self._root, parts, 0, {})

        if result is None:
            raise NotFound(f"No route matches {method} {path!r}")

        node, params = result

        # Check for catch-all at this node (if we consumed all parts)
        if method in node.routes_by_method:
            return RouteMatch(route=node.routes_by_method[method], path_params=params)

        # Method not allowed?
        if node.routes_by_method:
            all_methods = frozenset(node.routes_by_method)
            raise MethodNotAllowed(all_methods)

        raise NotFound(f"No route matches {method} {path!r}")

    def _match_node(
        self,
        node: _TrieNode,
        parts: list[str],
        index: int,
        params: dict[str, str],
    ) -> tuple[_TrieNode, dict[str, str]] | None:
        """Recursively match path parts against the trie."""
        # All parts consumed — return this node
        if index == len(parts):
            if node.routes_by_method:
                return node, params
            return None

        part = parts[index]

        # 1. Try static child first (exact match)
        if part in node.children:
            result = self._match_node(node.children[part], parts, index + 1, params)
            if result is not None:
                return result

        # 2. Try parameter child
        if node.param_child is not None:
            edge = node.param_child
            if edge.regex.match(part):
                new_params = {**params, edge.param_name: part}
                result = self._match_node(edge.node, parts, index + 1, new_params)
                if result is not None:
                    return result

        # 3. Try catch-all
        if node.catch_all_route is not None:
            remaining = "/".join(parts[index:])
            new_params = {**params, node.catch_all_route.param_name: remaining}
            # Create a synthetic node with the catch-all routes
            synthetic = _TrieNode()
            synthetic.routes_by_method = node.catch_all_route.route_by_method
            return synthetic, new_params

        return None

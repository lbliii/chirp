"""Route and RouteMatch frozen dataclasses."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PathSegment:
    """A parsed segment of a route path.

    Static:  ``/users``  (is_param=False)
    Param:   ``/{id}``   (is_param=True, param_name="id")
    Typed:   ``/{id:int}`` (is_param=True, param_name="id", param_type="int")
    """

    value: str
    is_param: bool = False
    param_name: str | None = None
    param_type: str = "str"


@dataclass(frozen=True, slots=True)
class Route:
    """A frozen route definition.

    Created during app setup, compiled into the router at freeze time.
    """

    path: str
    handler: Callable[..., Any]
    methods: frozenset[str]
    name: str | None = None
    referenced: bool = False


@dataclass(frozen=True, slots=True)
class RouteMatch:
    """Result of a successful route match."""

    route: Route
    path_params: dict[str, str]

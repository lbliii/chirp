"""Tests for chirp.routing.route — Route, RouteMatch, PathSegment."""

import pytest

from chirp.routing.route import PathSegment, Route, RouteMatch


def _handler() -> str:
    return "ok"


class TestPathSegment:
    def test_static(self) -> None:
        seg = PathSegment(value="users")
        assert seg.value == "users"
        assert seg.is_param is False
        assert seg.param_name is None
        assert seg.param_type == "str"

    def test_param(self) -> None:
        seg = PathSegment(value="{id}", is_param=True, param_name="id", param_type="int")
        assert seg.is_param is True
        assert seg.param_name == "id"
        assert seg.param_type == "int"

    def test_frozen(self) -> None:
        seg = PathSegment(value="users")
        with pytest.raises(AttributeError):
            seg.value = "other"  # type: ignore[misc]


class TestRoute:
    def test_creation(self) -> None:
        route = Route(path="/users", handler=_handler, methods=frozenset({"GET"}))
        assert route.path == "/users"
        assert route.handler is _handler
        assert route.methods == frozenset({"GET"})
        assert route.name is None

    def test_named_route(self) -> None:
        route = Route(
            path="/users", handler=_handler, methods=frozenset({"GET"}), name="user_list"
        )
        assert route.name == "user_list"

    def test_frozen(self) -> None:
        route = Route(path="/", handler=_handler, methods=frozenset({"GET"}))
        with pytest.raises(AttributeError):
            route.path = "/other"  # type: ignore[misc]


class TestRouteMatch:
    def test_creation(self) -> None:
        route = Route(path="/users/{id}", handler=_handler, methods=frozenset({"GET"}))
        match = RouteMatch(route=route, path_params={"id": "42"})
        assert match.route is route
        assert match.path_params == {"id": "42"}

    def test_frozen(self) -> None:
        route = Route(path="/", handler=_handler, methods=frozenset({"GET"}))
        match = RouteMatch(route=route, path_params={})
        with pytest.raises(AttributeError):
            match.route = route  # type: ignore[misc]

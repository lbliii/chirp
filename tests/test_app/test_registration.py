"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import pytest

from chirp import App


class TestAppRegistration:
    def test_route_decorator(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "hello"

        assert len(app._pending_routes) == 1
        assert app._pending_routes[0].path == "/"

    def test_route_with_methods(self) -> None:
        app = App()

        @app.route("/users", methods=["GET", "POST"])
        def users():
            return "users"

        assert app._pending_routes[0].methods == ["GET", "POST"]

    def test_error_decorator(self) -> None:
        app = App()

        @app.error(404)
        def not_found():
            return "Not found"

        assert 404 in app._error_handlers

    def test_middleware_registration(self) -> None:
        app = App()

        async def my_mw(request, next):
            return await next(request)

        app.add_middleware(my_mw)
        assert len(app._middleware_list) == 1

    def test_template_filter(self) -> None:
        app = App()

        @app.template_filter()
        def currency(value: float) -> str:
            return f"${value:,.2f}"

        assert "currency" in app._template_filters

    def test_template_filter_custom_name(self) -> None:
        app = App()

        @app.template_filter(name="money")
        def currency(value: float) -> str:
            return f"${value:,.2f}"

        assert "money" in app._template_filters

    def test_template_global(self) -> None:
        app = App()

        @app.template_global()
        def site_name() -> str:
            return "My App"

        assert "site_name" in app._template_globals

"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

import pytest

from chirp import App
from chirp.http.request import Request
from chirp.testing import TestClient


class TestServiceInjection:
    """Tests for app.provide() — dependency injection via type annotations."""

    async def test_provide_injects_into_decorator_route(self) -> None:
        """Provider factory is called when handler param annotation matches."""

        class GreetingService:
            def greet(self, name: str) -> str:
                return f"Hello, {name}!"

        service = GreetingService()
        app = App()
        app.provide(GreetingService, lambda: service)

        @app.route("/greet/{name}")
        def greet(name: str, svc: GreetingService) -> str:
            return svc.greet(name)

        async with TestClient(app) as client:
            resp = await client.get("/greet/world")
            assert resp.status == 200
            assert resp.text == "Hello, world!"

    async def test_provide_does_not_shadow_path_params(self) -> None:
        """Path params take priority over providers with same type."""
        app = App()
        app.provide(str, lambda: "should-not-appear")

        @app.route("/echo/{msg}")
        def echo(msg: str) -> str:
            return msg

        async with TestClient(app) as client:
            resp = await client.get("/echo/hello")
            assert resp.status == 200
            assert resp.text == "hello"

    async def test_provide_multiple_services(self) -> None:
        """Multiple providers can be registered and injected together."""

        class ServiceA:
            value = "A"

        class ServiceB:
            value = "B"

        app = App()
        app.provide(ServiceA, ServiceA)
        app.provide(ServiceB, ServiceB)

        @app.route("/both")
        def both(a: ServiceA, b: ServiceB) -> str:
            return f"{a.value}+{b.value}"

        async with TestClient(app) as client:
            resp = await client.get("/both")
            assert resp.status == 200
            assert resp.text == "A+B"

    async def test_provide_with_request(self) -> None:
        """Provider injection works alongside Request injection."""

        class Counter:
            def __init__(self) -> None:
                self.count = 0

            def increment(self) -> int:
                self.count += 1
                return self.count

        counter = Counter()
        app = App()
        app.provide(Counter, lambda: counter)

        @app.route("/count")
        def count(request: Request, c: Counter) -> str:
            return f"{request.method}:{c.increment()}"

        async with TestClient(app) as client:
            resp = await client.get("/count")
            assert resp.status == 200
            assert resp.text == "GET:1"

    def test_provide_rejects_after_freeze(self) -> None:
        """Cannot register providers after app is frozen."""
        app = App()

        @app.route("/")
        def index():
            return "ok"

        # Force freeze by accessing internal _freeze
        app._freeze()

        with pytest.raises(RuntimeError):
            app.provide(str, lambda: "late")

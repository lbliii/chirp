"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

from chirp import App
from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.testing import TestClient


class TestAppE2E:
    """End-to-end tests using TestClient."""

    async def test_hello_world(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "Hello, World!"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert response.text == "Hello, World!"

    async def test_json_response(self) -> None:
        app = App()

        @app.route("/api/data")
        def data():
            return {"message": "hello", "count": 42}

        async with TestClient(app) as client:
            response = await client.get("/api/data")
            assert response.status == 200
            assert "application/json" in response.content_type

    async def test_path_params(self) -> None:
        app = App()

        @app.route("/users/{name}")
        def user(name: str):
            return f"Hello, {name}!"

        async with TestClient(app) as client:
            response = await client.get("/users/alice")
            assert response.status == 200
            assert response.text == "Hello, alice!"

    async def test_typed_path_params(self) -> None:
        app = App()

        @app.route("/users/{id:int}")
        def user(id: int):
            return {"id": id}

        async with TestClient(app) as client:
            response = await client.get("/users/42")
            assert response.status == 200
            assert "42" in response.text

    async def test_multiple_methods(self) -> None:
        app = App()

        @app.route("/items", methods=["GET"])
        def list_items():
            return "item list"

        @app.route("/items", methods=["POST"])
        def create_item():
            return ("created", 201)

        async with TestClient(app) as client:
            get_resp = await client.get("/items")
            assert get_resp.status == 200

            post_resp = await client.post("/items")
            assert post_resp.status == 201

    async def test_404_default(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404

    async def test_not_found_raised_in_handler(self) -> None:
        """NotFound raised inside a handler produces a 404 response.

        This is the same mechanism that allows context providers to
        raise NotFound and have chirp's error pipeline handle it.
        """
        from chirp.errors import NotFound

        app = App()

        @app.route("/items/{item_id}")
        def item(item_id: str):
            if item_id == "missing":
                raise NotFound(f"Item {item_id} not found")
            return f"Item: {item_id}"

        async with TestClient(app) as client:
            ok = await client.get("/items/abc")
            assert ok.status == 200
            assert ok.text == "Item: abc"

            missing = await client.get("/items/missing")
            assert missing.status == 404

    async def test_405_default(self) -> None:
        app = App()

        @app.route("/items", methods=["GET"])
        def items():
            return "items"

        async with TestClient(app) as client:
            response = await client.post("/items")
            assert response.status == 405

    async def test_async_handler(self) -> None:
        app = App()

        @app.route("/async")
        async def async_handler():
            return "async works"

        async with TestClient(app) as client:
            response = await client.get("/async")
            assert response.status == 200
            assert response.text == "async works"

    async def test_request_injection(self) -> None:
        app = App()

        @app.route("/echo")
        async def echo(request: Request):
            return f"method={request.method} path={request.path}"

        async with TestClient(app) as client:
            response = await client.get("/echo")
            assert "method=GET" in response.text
            assert "path=/echo" in response.text

    async def test_debug_bootstrap_asset_is_served(self) -> None:
        app = App(config=AppConfig(debug=True))

        @app.route("/")
        def index():
            return "<html><body>ok</body></html>"

        async with TestClient(app) as client:
            page = await client.get("/")
            assert "/__chirp/debug/htmx.js" in page.text

            asset = await client.get("/__chirp/debug/htmx.js")
            assert asset.status == 200
            assert "application/javascript" in asset.content_type
            assert "__chirpHtmxDebugBooted" in asset.text

    async def test_response_chaining(self) -> None:
        app = App()

        @app.route("/custom")
        def custom():
            return Response("Created").with_status(201).with_header("X-Custom", "yes")

        async with TestClient(app) as client:
            response = await client.get("/custom")
            assert response.status == 201

    async def test_redirect(self) -> None:
        from chirp.http.response import Redirect

        app = App()

        @app.route("/old")
        def old():
            return Redirect("/new")

        async with TestClient(app) as client:
            response = await client.get("/old")
            assert response.status == 302

    async def test_middleware(self) -> None:
        app = App()

        async def add_header(request: Request, next):
            response = await next(request)
            return response.with_header("x-middleware", "applied")

        app.add_middleware(add_header)

        @app.route("/")
        def index():
            return "hello"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert ("x-middleware", "applied") in response.headers

    async def test_fragment_request(self) -> None:
        app = App()

        @app.route("/search")
        def search(request: Request):
            if request.is_fragment:
                return "fragment only"
            return "full page"

        async with TestClient(app) as client:
            full = await client.get("/search")
            assert full.text == "full page"

            fragment = await client.fragment("/search")
            assert fragment.text == "fragment only"

    async def test_fragment_with_target(self) -> None:
        app = App()

        @app.route("/search")
        def search(request: Request):
            target = request.htmx_target or "none"
            return f"target={target}"

        async with TestClient(app) as client:
            response = await client.fragment("/search", target="#results")
            assert "target=#results" in response.text

    async def test_fragment_with_trigger(self) -> None:
        app = App()

        @app.route("/search")
        def search(request: Request):
            trigger = request.htmx_trigger or "none"
            return f"trigger={trigger}"

        async with TestClient(app) as client:
            response = await client.fragment("/search", trigger="search-btn")
            assert "trigger=search-btn" in response.text

    async def test_fragment_with_history_restore(self) -> None:
        app = App()

        @app.route("/page")
        def page(request: Request):
            if request.is_history_restore:
                return "full restore"
            if request.is_fragment:
                return "fragment"
            return "full page"

        async with TestClient(app) as client:
            response = await client.fragment("/page", history_restore=True)
            assert response.text == "full restore"

    async def test_tuple_status_override(self) -> None:
        app = App()

        @app.route("/created")
        def created():
            return ("Resource created", 201)

        async with TestClient(app) as client:
            response = await client.get("/created")
            assert response.status == 201
            assert response.text == "Resource created"

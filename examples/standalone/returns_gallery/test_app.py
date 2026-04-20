"""Verify every return type in the gallery renders through the ASGI pipeline."""

from chirp.testing import TestClient


class TestReturnsGallery:
    """One route per response type — each assertion proves the type's contract."""

    async def test_template_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "text/html" in response.content_type
            assert "<!doctype html>" in response.text.lower()
            assert "Chirp returns gallery" in response.text

    async def test_fragment_is_block_only(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/fragment")
            assert response.status == 200
            assert "<!doctype html>" not in response.text.lower()
            assert "Fragment value" in response.text

    async def test_page_full_for_browser(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/page")
            assert response.status == 200
            assert "<!doctype html>" in response.text.lower()

    async def test_page_fragment_for_htmx(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/page", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "<!doctype html>" not in response.text.lower()
            assert "Page value" in response.text

    async def test_oob_returns_multi_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/oob", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "hx-swap-oob" in response.text
            assert "oob-counter" in response.text

    async def test_stream_is_chunked(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/stream")
            assert response.status == 200
            assert "Top section" in response.text
            assert "Middle section" in response.text
            assert "Bottom section" in response.text

    async def test_suspense_ships_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/suspense")
            assert response.status == 200
            assert "Suspense demo" in response.text
            assert "skeleton" in response.text or "Stats" in response.text

    async def test_eventstream_is_sse(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/events")
            assert response.status == 200
            assert "text/event-stream" in response.content_type

    async def test_validation_error_returns_422(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/validate",
                data={"name": "", "email": "bad"},
                headers={"HX-Request": "true"},
            )
            assert response.status == 422
            assert "Name is required" in response.text

    async def test_validation_success_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/validate",
                data={"name": "Ada", "email": "ada@example.com"},
                headers={"HX-Request": "true"},
            )
            assert response.status == 200
            assert "Form accepted" in response.text

    async def test_mutation_htmx_returns_fragments(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mutate", headers={"HX-Request": "true"})
            assert response.status == 200
            assert "Counter" in response.text

    async def test_mutation_plain_post_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mutate")
            assert response.status == 303
            assert ("location", "/") in response.headers

    async def test_redirect_returns_303(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/redirect")
            assert response.status == 303
            assert ("location", "/") in response.headers

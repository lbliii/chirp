"""Tests for chirp.extraction — typed dataclass extraction from request data."""

from dataclasses import dataclass

import pytest

from chirp.app import App
from chirp.http.request import Request
from chirp.testing import TestClient


@dataclass(frozen=True, slots=True)
class SearchParams:
    q: str = ""
    offset: int = 0
    search_only: bool = False


@dataclass(frozen=True, slots=True)
class ChatMessage:
    message: str = ""


@dataclass(frozen=True, slots=True)
class SavePayload:
    content: str = ""
    version: int = 0
    user_id: str = "anonymous"


class TestExtractDataclass:
    """Unit tests for the extract_dataclass helper."""

    def test_extract_from_mapping(self) -> None:
        from chirp.extraction import extract_dataclass

        result = extract_dataclass(SearchParams, {"q": "hello", "offset": "10"})
        assert result.q == "hello"
        assert result.offset == 10
        assert result.search_only is False

    def test_extract_missing_uses_defaults(self) -> None:
        from chirp.extraction import extract_dataclass

        result = extract_dataclass(SearchParams, {})
        assert result.q == ""
        assert result.offset == 0
        assert result.search_only is False

    def test_extract_bool_conversion(self) -> None:
        from chirp.extraction import extract_dataclass

        result = extract_dataclass(SearchParams, {"search_only": "true"})
        assert result.search_only is True

        result2 = extract_dataclass(SearchParams, {"search_only": "0"})
        assert result2.search_only is False

    def test_extract_strips_strings(self) -> None:
        from chirp.extraction import extract_dataclass

        result = extract_dataclass(ChatMessage, {"message": "  hello  "})
        assert result.message == "hello"

    def test_is_extractable_dataclass(self) -> None:
        from chirp.extraction import is_extractable_dataclass

        assert is_extractable_dataclass(SearchParams) is True
        assert is_extractable_dataclass(str) is False
        assert is_extractable_dataclass(int) is False
        assert is_extractable_dataclass(Request) is False
        # Instances are not types
        assert is_extractable_dataclass(SearchParams()) is False


class TestQueryExtraction:
    """E2E tests: dataclass params extracted from query string on GET."""

    async def test_get_extracts_query_params(self) -> None:
        app = App()

        @app.route("/search")
        def search(params: SearchParams) -> str:
            return f"q={params.q} offset={params.offset} search_only={params.search_only}"

        async with TestClient(app) as client:
            resp = await client.get("/search?q=hello&offset=5&search_only=true")
            assert resp.status == 200
            assert resp.text == "q=hello offset=5 search_only=True"

    async def test_get_defaults_when_no_query(self) -> None:
        app = App()

        @app.route("/search")
        def search(params: SearchParams) -> str:
            return f"q={params.q!r} offset={params.offset}"

        async with TestClient(app) as client:
            resp = await client.get("/search")
            assert resp.status == 200
            assert resp.text == "q='' offset=0"

    async def test_get_with_path_params_and_extraction(self) -> None:
        """Path params and dataclass extraction coexist."""
        app = App()

        @app.route("/items/{item_id}")
        def item(item_id: str, params: SearchParams) -> str:
            return f"item={item_id} q={params.q}"

        async with TestClient(app) as client:
            resp = await client.get("/items/abc?q=filter")
            assert resp.status == 200
            assert resp.text == "item=abc q=filter"


class TestFormExtraction:
    """E2E tests: dataclass params extracted from form body on POST."""

    async def test_post_extracts_form_data(self) -> None:
        app = App()

        @app.route("/chat", methods=["POST"])
        async def chat(msg: ChatMessage) -> str:
            return f"message={msg.message}"

        async with TestClient(app) as client:
            resp = await client.post(
                "/chat",
                data={"message": "hello world"},
            )
            assert resp.status == 200
            assert resp.text == "message=hello world"

    async def test_post_extracts_json_body(self) -> None:
        app = App()

        @app.route("/save", methods=["POST"])
        async def save(payload: SavePayload) -> str:
            return f"content={payload.content} version={payload.version}"

        async with TestClient(app) as client:
            resp = await client.post(
                "/save",
                json={"content": "hello", "version": 3},
            )
            assert resp.status == 200
            assert resp.text == "content=hello version=3"

    async def test_post_with_provider_and_extraction(self) -> None:
        """Provider injection and form extraction work together."""

        class FakeStore:
            name = "fake"

        app = App()
        app.provide(FakeStore, FakeStore)

        @app.route("/submit", methods=["POST"])
        async def submit(store: FakeStore, msg: ChatMessage) -> str:
            return f"store={store.name} message={msg.message}"

        async with TestClient(app) as client:
            resp = await client.post(
                "/submit",
                data={"message": "hi"},
            )
            assert resp.status == 200
            assert resp.text == "store=fake message=hi"

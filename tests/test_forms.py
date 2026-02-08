"""Tests for form data parsing — URL-encoded and multipart."""

import pytest

from chirp.app import App
from chirp.http.forms import FormData, UploadFile, parse_form_data
from chirp.http.request import Request
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# FormData unit tests
# ---------------------------------------------------------------------------


class TestFormData:
    def test_getitem(self) -> None:
        form = FormData({"name": ["alice"]})
        assert form["name"] == "alice"

    def test_getitem_returns_first(self) -> None:
        form = FormData({"color": ["red", "blue"]})
        assert form["color"] == "red"

    def test_getitem_missing_raises(self) -> None:
        form = FormData({})
        with pytest.raises(KeyError):
            form["missing"]

    def test_get_with_default(self) -> None:
        form = FormData({})
        assert form.get("missing") is None
        assert form.get("missing", "fallback") == "fallback"

    def test_get_list(self) -> None:
        form = FormData({"tags": ["python", "web", "async"]})
        assert form.get_list("tags") == ["python", "web", "async"]

    def test_get_list_missing(self) -> None:
        form = FormData({})
        assert form.get_list("missing") == []

    def test_contains(self) -> None:
        form = FormData({"name": ["alice"]})
        assert "name" in form
        assert "age" not in form

    def test_iter(self) -> None:
        form = FormData({"a": ["1"], "b": ["2"]})
        assert set(form) == {"a", "b"}

    def test_len(self) -> None:
        form = FormData({"a": ["1"], "b": ["2"], "c": ["3"]})
        assert len(form) == 3

    def test_repr(self) -> None:
        form = FormData({"name": ["alice"]})
        assert "FormData" in repr(form)
        assert "alice" in repr(form)

    def test_files_empty_by_default(self) -> None:
        form = FormData({"x": ["1"]})
        assert len(form.files) == 0

    def test_files_access(self) -> None:
        upload = UploadFile(
            filename="test.txt",
            content_type="text/plain",
            size=5,
            _content=b"hello",
        )
        form = FormData({"name": ["alice"]}, files={"avatar": upload})
        assert form.files["avatar"].filename == "test.txt"


class TestUploadFile:
    async def test_read(self) -> None:
        f = UploadFile(filename="test.txt", content_type="text/plain", size=5, _content=b"hello")
        assert await f.read() == b"hello"

    async def test_save(self, tmp_path) -> None:
        f = UploadFile(filename="test.txt", content_type="text/plain", size=5, _content=b"hello")
        dest = tmp_path / "output.txt"
        await f.save(dest)
        assert dest.read_bytes() == b"hello"

    def test_repr(self) -> None:
        f = UploadFile(filename="photo.jpg", content_type="image/jpeg", size=1024, _content=b"x")
        assert "photo.jpg" in repr(f)
        assert "1024" in repr(f)


# ---------------------------------------------------------------------------
# parse_form_data unit tests
# ---------------------------------------------------------------------------


class TestParseUrlEncoded:
    async def test_basic(self) -> None:
        form = await parse_form_data(b"name=alice&age=30", "application/x-www-form-urlencoded")
        assert form["name"] == "alice"
        assert form["age"] == "30"

    async def test_multiple_values(self) -> None:
        form = await parse_form_data(b"tag=a&tag=b&tag=c", "application/x-www-form-urlencoded")
        assert form.get_list("tag") == ["a", "b", "c"]

    async def test_empty_body(self) -> None:
        form = await parse_form_data(b"", "application/x-www-form-urlencoded")
        assert len(form) == 0

    async def test_url_encoded_special_chars(self) -> None:
        form = await parse_form_data(
            b"q=hello+world&path=%2Ffoo", "application/x-www-form-urlencoded"
        )
        assert form["q"] == "hello world"
        assert form["path"] == "/foo"


class TestParseUnsupported:
    async def test_unsupported_content_type(self) -> None:
        with pytest.raises(ValueError, match="Unsupported form content type"):
            await parse_form_data(b"data", "application/json")


# ---------------------------------------------------------------------------
# request.form() integration
# ---------------------------------------------------------------------------


class TestRequestForm:
    async def test_form_urlencoded(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await request.form()
            return f"name={form['name']}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=alice",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert response.text == "name=alice"

    async def test_form_cached(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form1 = await request.form()
            form2 = await request.form()
            same = form1 is form2
            return f"cached={same}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"x=1",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "cached=True"

    async def test_form_default_content_type(self) -> None:
        """When no Content-Type header, defaults to urlencoded."""
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await request.form()
            return f"val={form.get('key', 'none')}"

        async with TestClient(app) as client:
            response = await client.post("/submit", body=b"key=value")
            assert response.status == 200
            assert response.text == "val=value"

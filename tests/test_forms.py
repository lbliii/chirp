"""Tests for form data parsing, binding, and multipart."""

from dataclasses import dataclass

import pytest

from chirp.app import App
from chirp.templating.returns import ValidationError
from chirp.http.forms import (
    FormBindingError,
    FormData,
    UploadFile,
    form_from,
    form_or_errors,
    form_values,
    parse_form_data,
)
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


# ---------------------------------------------------------------------------
# form_from() — dataclass binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SimpleForm:
    title: str
    description: str = ""
    priority: str = "medium"


@dataclass(frozen=True, slots=True)
class TypedForm:
    name: str
    age: int
    score: float = 0.0
    active: bool = True


@dataclass(frozen=True, slots=True)
class OptionalForm:
    name: str
    nickname: str | None = None


class TestFormFrom:
    """Tests for form_from() — dataclass form binding."""

    async def test_basic_binding(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, SimpleForm)
            return f"{form.title}|{form.description}|{form.priority}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=My+Task&description=Do+stuff&priority=high",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "My Task|Do stuff|high"

    async def test_defaults_applied(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, SimpleForm)
            return f"{form.title}|{form.description}|{form.priority}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=Test",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "Test||medium"

    async def test_missing_required_field(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            try:
                form = await form_from(request, SimpleForm)
                return f"ok: {form.title}"
            except FormBindingError as e:
                return f"error: {sorted(e.errors.keys())}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "error:" in response.text
            assert "title" in response.text

    async def test_int_coercion(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, TypedForm)
            return f"{form.name}|{form.age}|{type(form.age).__name__}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Alice&age=30",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "Alice|30|int"

    async def test_float_coercion(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, TypedForm)
            return f"{form.score}|{type(form.score).__name__}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Bob&age=25&score=9.5",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "9.5|float"

    async def test_bool_coercion(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, TypedForm)
            return f"{form.active}|{type(form.active).__name__}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Bob&age=25&active=on",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "True|bool"

    async def test_invalid_int_raises_binding_error(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            try:
                form = await form_from(request, TypedForm)
                return "ok"
            except FormBindingError as e:
                return f"error: {sorted(e.errors.keys())}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Alice&age=notanumber",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "age" in response.text

    async def test_whitespace_stripped(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, SimpleForm)
            return f"[{form.title}]"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=++Hello++",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "[Hello]"

    async def test_optional_field_none(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, OptionalForm)
            return f"{form.name}|{form.nickname}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Alice",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "Alice|None"


# ---------------------------------------------------------------------------
# form_or_errors() — glue function
# ---------------------------------------------------------------------------


class TestFormOrErrors:
    """Tests for form_or_errors() — bind or return ValidationError."""

    async def test_success_returns_dataclass(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body"
            )
            if isinstance(result, ValidationError):
                return "error"
            return f"ok:{result.title}|{result.priority}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=Hello&priority=high",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "ok:Hello|high"

    async def test_failure_returns_validation_error(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body"
            )
            if isinstance(result, ValidationError):
                return f"errors:{sorted(result.context['errors'].keys())}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "title" in response.text

    async def test_failure_includes_form_values(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body"
            )
            if isinstance(result, ValidationError):
                return f"form:{result.context.get('form', {})}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "description" in response.text
            assert "stuff" in response.text

    async def test_extra_context_passed_through(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body",
                columns=["todo", "done"],
            )
            if isinstance(result, ValidationError):
                return f"columns:{result.context.get('columns')}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "todo" in response.text

    async def test_retarget_passed_through(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body",
                retarget="#errors",
            )
            if isinstance(result, ValidationError):
                return f"retarget:{result.retarget}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "retarget:#errors"

    async def test_template_and_block_name(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "tasks.html", "task_form"
            )
            if isinstance(result, ValidationError):
                return f"{result.template_name}|{result.block_name}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "tasks.html|task_form"

    async def test_type_coercion_error_returns_validation_error(self) -> None:
        """FormBindingError from invalid type coercion, not just missing fields."""
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, TypedForm, "form.html", "form_body"
            )
            if isinstance(result, ValidationError):
                return f"errors:{sorted(result.context['errors'].keys())}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"name=Alice&age=notanumber",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "age" in response.text

    async def test_success_with_defaults(self) -> None:
        """Defaults are applied when optional fields are omitted."""
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(
                request, SimpleForm, "form.html", "form_body"
            )
            if isinstance(result, ValidationError):
                return "error"
            return f"{result.title}|{result.description}|{result.priority}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=Hello",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "Hello||medium"


# ---------------------------------------------------------------------------
# form_values() — dataclass/Mapping to dict[str, str]
# ---------------------------------------------------------------------------


class TestFormValues:
    """Tests for form_values() — extract values for template re-population."""

    def test_dataclass_input(self) -> None:
        form = SimpleForm(title="Hello", description="World", priority="high")
        result = form_values(form)
        assert result == {"title": "Hello", "description": "World", "priority": "high"}

    def test_dataclass_none_becomes_empty_string(self) -> None:
        form = OptionalForm(name="Alice", nickname=None)
        result = form_values(form)
        assert result == {"name": "Alice", "nickname": ""}

    def test_dataclass_int_to_string(self) -> None:
        form = TypedForm(name="Bob", age=25, score=9.5, active=True)
        result = form_values(form)
        assert result == {
            "name": "Bob",
            "age": "25",
            "score": "9.5",
            "active": "True",
        }

    def test_mapping_input(self) -> None:
        result = form_values({"title": "Hello", "count": 5})
        assert result == {"title": "Hello", "count": "5"}

    def test_unknown_type_returns_empty(self) -> None:
        result = form_values("not a form")
        assert result == {}

    def test_empty_dataclass(self) -> None:
        @dataclass(frozen=True, slots=True)
        class EmptyForm:
            pass

        result = form_values(EmptyForm())
        assert result == {}

    def test_empty_mapping(self) -> None:
        result = form_values({})
        assert result == {}

    def test_formdata_input(self) -> None:
        """FormData is a Mapping — form_values should handle it."""
        fd = FormData({"name": ["Alice"], "email": ["alice@test.com"]})
        result = form_values(fd)
        assert result == {"name": "Alice", "email": "alice@test.com"}


# ---------------------------------------------------------------------------
# Top-level import smoke test
# ---------------------------------------------------------------------------


class TestTopLevelImports:
    """Verify form helpers are importable from the chirp top-level."""

    def test_import_form_or_errors(self) -> None:
        from chirp import form_or_errors as fn

        assert callable(fn)

    def test_import_form_values(self) -> None:
        from chirp import form_values as fn

        assert callable(fn)

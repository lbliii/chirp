"""Tests for form data parsing, binding, and multipart."""

from dataclasses import dataclass
from typing import Annotated

import pytest

from chirp import App
from chirp.config import AppConfig
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
from chirp.templating.returns import ValidationError
from chirp.testing import TestClient
from chirp.validation import max_length, required

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
        upload = UploadFile.from_bytes(
            filename="test.txt",
            content_type="text/plain",
            content=b"hello",
        )
        form = FormData({"name": ["alice"]}, files={"avatar": upload})
        assert form.files["avatar"].filename == "test.txt"


class TestUploadFile:
    async def test_read(self) -> None:
        f = UploadFile.from_bytes(filename="test.txt", content_type="text/plain", content=b"hello")
        assert await f.read() == b"hello"

    async def test_save(self, tmp_path) -> None:
        f = UploadFile.from_bytes(filename="test.txt", content_type="text/plain", content=b"hello")
        dest = tmp_path / "output.txt"
        await f.save(dest)
        assert dest.read_bytes() == b"hello"

    def test_repr(self) -> None:
        f = UploadFile.from_bytes(
            filename="photo.jpg", content_type="image/jpeg", content=b"x" * 1024
        )
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
        with pytest.raises(ValueError, match="Unsupported form content type") as exc_info:
            await parse_form_data(b"data", "application/json")
        msg = str(exc_info.value)
        assert "Unsupported form content type" in msg
        assert "application/x-www-form-urlencoded" in msg
        assert "multipart/form-data" in msg
        assert "request.body" in msg

    async def test_multipart_missing_boundary_message_is_actionable(self) -> None:
        with pytest.raises(ValueError, match="missing boundary") as exc_info:
            await parse_form_data(b"data", "multipart/form-data")
        msg = str(exc_info.value)
        assert "missing boundary" in msg
        assert "multipart/form-data; boundary=..." in msg


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


@dataclass(frozen=True, slots=True)
class ListForm:
    title: str
    item_ids: list[int]


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
                await form_from(request, TypedForm)
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

    async def test_repeated_list_field_binding(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, ListForm)
            return f"{form.title}|{form.item_ids}|{type(form.item_ids[0]).__name__}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                data={"title": "Batch", "item_ids": ["1", "3"]},
            )
            assert response.text == "Batch|[1, 3]|int"

    async def test_missing_list_field_defaults_to_empty_list(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            form = await form_from(request, ListForm)
            return f"{form.title}|{form.item_ids}"

        async with TestClient(app) as client:
            response = await client.post("/submit", data={"title": "Batch"})
            assert response.text == "Batch|[]"

    async def test_invalid_list_item_raises_binding_error(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            try:
                await form_from(request, ListForm)
                return "ok"
            except FormBindingError as e:
                return f"error: {e.errors['item_ids'][0]}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                data={"title": "Batch", "item_ids": ["1", "nope"]},
            )
            assert "expected list[int]" in response.text


# ---------------------------------------------------------------------------
# form_or_errors() — glue function
# ---------------------------------------------------------------------------


class TestFormOrErrors:
    """Tests for form_or_errors() — bind or return ValidationError."""

    async def test_success_returns_dataclass(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
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
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
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
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
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
                request,
                SimpleForm,
                "form.html",
                "form_body",
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
                request,
                SimpleForm,
                "form.html",
                "form_body",
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
            result = await form_or_errors(request, SimpleForm, "tasks.html", "task_form")
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
            result = await form_or_errors(request, TypedForm, "form.html", "form_body")
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
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
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
# form_or_errors() — unified bind + Annotated validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnnotatedForm:
    """One declarative schema: binding + per-field rules via Annotated."""

    title: Annotated[str, required, max_length(5)]
    note: str = ""


@dataclass(frozen=True, slots=True)
class MixedForm:
    """A binding-typed field plus a separately-validated Annotated field."""

    age: int
    name: Annotated[str, required, max_length(3)]


@dataclass(frozen=True, slots=True)
class FalsyForm:
    """Falsy-but-valid values: "0" satisfies required; an empty list is fine."""

    count: Annotated[str, required]
    tags: list[str]


class TestUnifiedValidation:
    """form_or_errors runs Annotated rules in the same pass as binding."""

    async def test_valid_annotated_binds_instance(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, AnnotatedForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return "error"
            return f"ok:{result.title}|{result.note}"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=Hi&note=howdy",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "ok:Hi|howdy"

    async def test_rule_failure_returns_validation_error_with_messages(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, AnnotatedForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                msgs = result.context["errors"].get("title", [])
                return f"errors:{'|'.join(msgs)}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=waytoolong&note=hi",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "Must be at most 5 characters" in response.text

    async def test_required_rule_failure_on_empty(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, AnnotatedForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return f"errors:{sorted(result.context['errors'].keys())}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=&note=hi",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "title" in response.text

    async def test_failure_repopulates_raw_form_values(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, AnnotatedForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return f"form:{result.context.get('form', {})}"
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/submit",
                body=b"title=waytoolong&note=keepme",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # The raw (unbound) submitted values are echoed back for re-render.
            assert "waytoolong" in response.text
            assert "keepme" in response.text

    async def test_binding_and_rule_errors_merge(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, MixedForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return f"errors:{sorted(result.context['errors'].keys())}"
            return "ok"

        async with TestClient(app) as client:
            # age fails binding (int coercion), name fails the max_length rule.
            response = await client.post(
                "/submit",
                body=b"age=abc&name=toolong",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # Both fields surface in the merged error map.
            assert "age" in response.text
            assert "name" in response.text

    async def test_falsy_valid_values_not_flagged(self) -> None:
        app = App()

        @app.route("/submit", methods=["POST"])
        async def submit(request: Request):
            result = await form_or_errors(request, FalsyForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return f"error:{sorted(result.context['errors'].keys())}"
            return f"ok:{result.count}|{result.tags}"

        async with TestClient(app) as client:
            # count="0" satisfies required; tags omitted binds to [] (valid).
            response = await client.post(
                "/submit",
                body=b"count=0",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.text == "ok:0|[]"

    async def test_plain_dataclass_unchanged(self) -> None:
        """No Annotated rules → behavior identical to the binding-only path."""
        app = App()

        @app.route("/ok", methods=["POST"])
        async def ok(request: Request):
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return "error"
            return f"ok:{result.title}|{result.priority}"

        @app.route("/missing", methods=["POST"])
        async def missing(request: Request):
            result = await form_or_errors(request, SimpleForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return f"errors:{sorted(result.context['errors'].keys())}"
            return "ok"

        async with TestClient(app) as client:
            good = await client.post(
                "/ok",
                body=b"title=Hello&priority=high",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert good.text == "ok:Hello|high"

            bad = await client.post(
                "/missing",
                body=b"description=stuff",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # Missing required "title" still raises FormBindingError → ValidationError.
            assert "title" in bad.text


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


# ---------------------------------------------------------------------------
# Upload spooling + limits (issue #177)
# ---------------------------------------------------------------------------


def _multipart_body(parts: list[tuple[str, str | None, bytes]], boundary: str = "BOUND") -> bytes:
    """Build a multipart/form-data body.

    Each part is (field_name, filename_or_None, content_bytes).
    """
    chunks: list[bytes] = []
    for name, filename, content in parts:
        chunks.append(f"--{boundary}\r\n".encode())
        if filename is not None:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
            )
            chunks.append(b"Content-Type: application/octet-stream\r\n")
        else:
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n'.encode())
        chunks.append(b"\r\n")
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)


_MP_CT = "multipart/form-data; boundary=BOUND"


class TestUploadSpooling:
    async def test_small_upload_stays_in_memory(self) -> None:
        body = _multipart_body([("avatar", "a.bin", b"small")])
        form = await parse_form_data(body, _MP_CT, spool_threshold=1024 * 1024)
        upload = form.files["avatar"]
        assert await upload.read() == b"small"
        assert upload.spilled_to_disk is False

    async def test_large_upload_spills_to_disk(self) -> None:
        # Threshold of 100 bytes, payload of 5000 bytes → must roll to disk.
        payload = b"x" * 5000
        body = _multipart_body([("big", "big.bin", payload)])
        form = await parse_form_data(body, _MP_CT, spool_threshold=100)
        upload = form.files["big"]
        assert upload.size == 5000
        assert upload.spilled_to_disk is True, "large upload should not be held in RAM"
        assert await upload.read() == payload

    async def test_max_parts_cap_rejects_bomb(self) -> None:
        from chirp.errors import PayloadTooLarge

        # 5 parts, cap at 3 → multipart bomb guard fires.
        parts = [(f"f{i}", None, b"v") for i in range(5)]
        body = _multipart_body(parts)
        with pytest.raises(PayloadTooLarge):
            await parse_form_data(body, _MP_CT, max_parts=3)

    async def test_max_parts_unbounded_by_default(self) -> None:
        parts = [(f"f{i}", None, b"v") for i in range(50)]
        body = _multipart_body(parts)
        form = await parse_form_data(body, _MP_CT)  # no max_parts
        assert len(form) == 50

    async def test_save_in_memory_upload(self, tmp_path) -> None:
        body = _multipart_body([("doc", "doc.txt", b"hello world")])
        form = await parse_form_data(body, _MP_CT, spool_threshold=1024 * 1024)
        dest = tmp_path / "out.txt"
        await form.files["doc"].save(dest)
        assert dest.read_bytes() == b"hello world"

    async def test_save_spilled_upload(self, tmp_path) -> None:
        payload = b"y" * 4096
        body = _multipart_body([("doc", "doc.bin", payload)])
        form = await parse_form_data(body, _MP_CT, spool_threshold=64)
        upload = form.files["doc"]
        assert upload.spilled_to_disk is True
        dest = tmp_path / "out.bin"
        await upload.save(dest)
        assert dest.read_bytes() == payload


class TestUploadFilenameSanitization:
    async def test_save_rejects_traversal_path(self, tmp_path) -> None:
        # The realistic sink: handler joins an attacker-controlled upload
        # filename onto a chosen directory. A traversal attempt is rejected
        # outright rather than silently escaping the directory.
        f = UploadFile.from_bytes(filename="x", content_type="text/plain", content=b"pwned")
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        with pytest.raises(ValueError, match="traversal"):
            await f.save(upload_dir / "../../etc/passwd")
        assert not (tmp_path / "etc").exists()
        assert not (tmp_path.parent / "passwd").exists()

    async def test_save_sanitizes_basename_separators(self, tmp_path) -> None:
        # A filename with a leading slash (no '..') is reduced to its basename
        # inside the caller's directory.
        f = UploadFile.from_bytes(filename="x", content_type="text/plain", content=b"data")
        await f.save(tmp_path / "evil.txt")
        assert (tmp_path / "evil.txt").read_bytes() == b"data"

    async def test_save_rejects_dotdot_only_basename(self, tmp_path) -> None:
        f = UploadFile.from_bytes(filename="x", content_type="text/plain", content=b"data")
        # Path("/x/..").parts contains '..', so this is rejected as traversal.
        with pytest.raises(ValueError, match="traversal"):
            await f.save(tmp_path / "..")

    def test_sanitize_helper_rejects_traversal(self) -> None:
        from chirp.http.forms import _sanitize_upload_filename

        assert _sanitize_upload_filename("../../etc/passwd") == "passwd"
        assert _sanitize_upload_filename("/abs/path/file.txt") == "file.txt"
        assert _sanitize_upload_filename("C:\\windows\\evil.exe") == "evil.exe"
        assert _sanitize_upload_filename("..") == "upload"
        assert _sanitize_upload_filename("with\x00nul") == "withnul"


class TestBodySizeLimit:
    """The GENERAL request-body cap (max_request_body_size) applies to every
    content type — JSON, text, urlencoded, multipart — enforced in stream()."""

    async def test_oversize_body_rejected_413(self) -> None:
        from chirp.errors import PayloadTooLarge

        app = App(AppConfig(max_request_body_size=10, max_upload_size=10))

        @app.route("/upload", methods=["POST"])
        async def upload(request: Request):
            try:
                await request.body()
            except PayloadTooLarge:
                return "rejected"
            return "accepted"

        async with TestClient(app) as client:
            response = await client.post("/upload", body=b"x" * 100)
            assert response.text == "rejected"

    async def test_within_limit_accepted(self) -> None:
        app = App(AppConfig(max_request_body_size=1000, max_upload_size=1000))

        @app.route("/upload", methods=["POST"])
        async def upload(request: Request):
            data = await request.body()
            return f"got {len(data)}"

        async with TestClient(app) as client:
            response = await client.post("/upload", body=b"x" * 100)
            assert response.text == "got 100"

    async def test_oversize_surfaces_413_status(self) -> None:
        app = App(AppConfig(max_request_body_size=10, max_upload_size=10))

        @app.route("/upload", methods=["POST"])
        async def upload(request: Request):
            await request.body()  # raises PayloadTooLarge → 413
            return "ok"

        async with TestClient(app) as client:
            response = await client.post("/upload", body=b"x" * 100)
            assert response.status == 413

    async def test_json_body_capped_by_general_limit(self) -> None:
        """A non-multipart (JSON) body is governed by max_request_body_size,
        not max_upload_size — the two knobs are independent."""
        app = App(AppConfig(max_request_body_size=10, max_upload_size=10))

        @app.route("/api", methods=["POST"])
        async def api(request: Request):
            await request.body()
            return "ok"

        async with TestClient(app) as client:
            response = await client.post("/api", body=b'{"k":"vvvvvvvvvv"}')
            assert response.status == 413

    async def test_stream_aborts_before_full_buffer(self) -> None:
        """stream() must raise before the overflowing chunk is buffered."""
        from chirp.errors import PayloadTooLarge

        req = Request.from_asgi(
            {"type": "http", "method": "POST", "path": "/", "headers": []},
            _make_receive([b"a" * 6, b"b" * 6]),
            max_request_body_size=10,
        )
        seen = 0

        async def _consume() -> None:
            nonlocal seen
            async for chunk in req.stream():
                seen += len(chunk)

        with pytest.raises(PayloadTooLarge):
            await _consume()
        # First 6-byte chunk yielded (under limit); second pushes over and raises.
        assert seen == 6

    async def test_body_cache_not_poisoned_on_overflow(self) -> None:
        from chirp.errors import PayloadTooLarge

        req = Request.from_asgi(
            {"type": "http", "method": "POST", "path": "/", "headers": []},
            _make_receive([b"x" * 100]),
            max_request_body_size=10,
        )
        with pytest.raises(PayloadTooLarge):
            await req.body()
        assert "_body" not in req._cache


class TestMultipartTotalSizeLimit:
    """max_upload_size caps the cumulative size of multipart parts only — the
    multipart-specific inner envelope, distinct from max_request_body_size."""

    async def test_oversize_multipart_rejected(self) -> None:
        from chirp.errors import PayloadTooLarge

        body = _multipart_body([("big", "big.bin", b"x" * 5000)])
        with pytest.raises(PayloadTooLarge, match="total size"):
            await parse_form_data(body, _MP_CT, max_total_size=100)

    async def test_multipart_within_total_accepted(self) -> None:
        body = _multipart_body([("doc", "doc.bin", b"x" * 50)])
        form = await parse_form_data(body, _MP_CT, max_total_size=1000)
        assert form.files["doc"].size == 50

    async def test_multipart_total_unbounded_by_default(self) -> None:
        body = _multipart_body([("doc", "doc.bin", b"x" * 5000)])
        form = await parse_form_data(body, _MP_CT)  # no max_total_size
        assert form.files["doc"].size == 5000

    async def test_multipart_total_accumulates_across_parts(self) -> None:
        from chirp.errors import PayloadTooLarge

        # Two 60-byte parts = 120 bytes total > 100 cap, though no single part
        # exceeds the cap on its own.
        body = _multipart_body([("a", "a.bin", b"x" * 60), ("b", "b.bin", b"y" * 60)])
        with pytest.raises(PayloadTooLarge, match="total size"):
            await parse_form_data(body, _MP_CT, max_total_size=100)


class TestUploadFileImmutability:
    """UploadFile metadata is immutable (frozen dataclass) — issue #197."""

    def test_metadata_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        f = UploadFile.from_bytes(filename="a.txt", content_type="text/plain", content=b"x")
        with pytest.raises(FrozenInstanceError):
            f.filename = "evil.txt"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            f.content_type = "text/html"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            f.size = 999  # type: ignore[misc]

    async def test_spool_still_usable_while_frozen(self) -> None:
        # Frozen forbids rebinding fields, not mutating the IO object a field
        # points to: read() seeks and reads the spool fine.
        f = UploadFile.from_bytes(filename="a.txt", content_type="text/plain", content=b"hello")
        assert await f.read() == b"hello"
        assert await f.read() == b"hello"  # re-readable


class TestBodyReadOnceCached:
    async def test_body_cached_across_calls(self) -> None:
        app = App()

        @app.route("/echo", methods=["POST"])
        async def echo(request: Request):
            b1 = await request.body()
            b2 = await request.body()
            return f"{b1 == b2}|{b1.decode()}"

        async with TestClient(app) as client:
            response = await client.post("/echo", body=b"payload")
            assert response.text == "True|payload"


def _make_receive(chunks: list[bytes]):
    """Build an ASGI receive callable yielding the given body chunks."""
    queue = list(chunks)

    async def receive():
        if queue:
            body = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(queue)}
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive

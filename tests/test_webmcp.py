"""Declarative WebMCP form projection proof for issue #574."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pytest

from chirp import App, AppConfig, Page, Request, ValidationError, WebMCPForm, form_or_errors
from chirp.contracts import FormContract, contract
from chirp.errors import ConfigurationError
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(574)


def test_preview_is_pinned_to_the_reviewed_proposal_commit() -> None:
    assert WebMCPForm.proposal_commit == "0b676d27a08aafd3b4f8a709756eeeab342fd9bd"


class _StartTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.tags.append((tag, dict(attrs)))


def _write_template(
    path: Path,
    *,
    projected: bool = True,
    tool_name: str = "tasks.create",
) -> None:
    form_attrs = f'{{{{ webmcp_form_attrs("{tool_name}") }}}}' if projected else ""
    title_attrs = (
        f'{{{{ webmcp_control_attrs("{tool_name}", "title") }}}}'
        if projected
        else ' type="text" name="title" required'
    )
    priority_attrs = (
        f'{{{{ webmcp_control_attrs("{tool_name}", "priority") }}}}'
        if projected
        else ' type="number" name="priority" value="2"'
    )
    path.joinpath("tasks.html").write_text(
        "{% block page_root %}<!doctype html><html><body>"
        "{% block form %}"
        f'<form id="task-form" method="post" action="/tasks"{form_attrs}>'
        "{% if csrf_field is defined %}{{ csrf_field() }}{% end %}"
        f'<input id="title"{title_attrs}>'
        f'<input id="priority"{priority_attrs}>'
        "{% for message in errors | field_errors('title') %}"
        "<p class='error'>{{ message }}</p>{% end %}"
        "<button type='submit'>Create</button></form>"
        "{% end %}</body></html>{% end %}",
        encoding="utf-8",
    )


@dataclass(frozen=True, slots=True)
class _TaskForm:
    title: str = field(
        metadata={
            "webmcp_control": "text",
            "webmcp_description": 'Task title, such as "Ship docs"',
            "webmcp_min_length": 1,
            "webmcp_max_length": 80,
            "webmcp_pattern": r"[^<>]+",
        }
    )
    priority: int = field(
        default=2,
        metadata={
            "webmcp_control": "number",
            "webmcp_description": "Priority from one to three",
            "webmcp_min": 1,
            "webmcp_max": 3,
            "webmcp_step": 1,
        },
    )


def _projected_app(tmp_path: Path, *, csrf: bool = False) -> App:
    _write_template(tmp_path)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))
    if csrf:
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(CSRFMiddleware())
    form_contract = FormContract(
        _TaskForm,
        "tasks.html",
        "form",
        webmcp=WebMCPForm(
            "tasks.create",
            'Create a task safely, even when the title contains "quotes".',
        ),
    )

    @app.route("/", template="tasks.html")
    def index() -> Page:
        return Page("tasks.html", "form", page_block_name="page_root", errors={})

    @app.route("/tasks", methods=["POST"])
    @contract(form=form_contract)
    async def create(request: Request) -> Page | ValidationError:
        result = await form_or_errors(request, _TaskForm, "tasks.html", "form")
        if isinstance(result, ValidationError):
            return result
        return Page(
            "tasks.html",
            "form",
            page_block_name="page_root",
            errors={},
            created=result.title,
        )

    return app


async def test_projection_renders_exact_escaped_attributes_on_real_form(tmp_path: Path) -> None:
    app = _projected_app(tmp_path)

    async with TestClient(app) as client:
        response = await client.get("/")

    parser = _StartTags()
    parser.feed(response.text)
    tags_by_id = {
        attrs["id"]: (tag, attrs)
        for tag, attrs in parser.tags
        if attrs.get("id") in {"task-form", "title", "priority"}
    }
    form_tag, form_attrs = tags_by_id["task-form"]
    assert form_tag == "form"
    assert form_attrs["method"] == "post"
    assert form_attrs["action"] == "/tasks"
    assert form_attrs["toolname"] == "tasks.create"
    assert form_attrs["tooldescription"] == (
        'Create a task safely, even when the title contains "quotes".'
    )
    assert "&quot;quotes&quot;" in response.text
    assert "toolautosubmit" not in form_attrs

    _, title_attrs = tags_by_id["title"]
    assert title_attrs == {
        "id": "title",
        "type": "text",
        "name": "title",
        "required": None,
        "toolparamdescription": 'Task title, such as "Ship docs"',
        "maxlength": "80",
        "minlength": "1",
        "pattern": "[^<>]+",
    }
    _, priority_attrs = tags_by_id["priority"]
    assert priority_attrs["type"] == "number"
    assert priority_attrs["name"] == "priority"
    assert priority_attrs["value"] == "2"
    assert priority_attrs["min"] == "1"
    assert priority_attrs["max"] == "3"
    assert priority_attrs["step"] == "1"
    assert "required" not in priority_attrs
    assert "document.modelContext" not in response.text


async def test_normal_and_htmx_submissions_share_binding_and_validation(tmp_path: Path) -> None:
    app = _projected_app(tmp_path)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with TestClient(app) as client:
        valid = await client.post("/tasks", body=b"title=Release&priority=1", headers=headers)
        invalid = await client.post("/tasks", body=b"priority=1", headers=headers)
        htmx = await client.post(
            "/tasks",
            body=b"title=Fragment&priority=3",
            headers={**headers, "HX-Request": "true", "HX-Target": "task-form"},
        )

    assert valid.status == 200
    assert "<!doctype html>" in valid.text.lower()
    assert invalid.status == 422
    assert "title is required" in invalid.text
    assert htmx.status == 200
    assert "<!doctype html>" not in htmx.text.lower()
    assert 'toolname="tasks.create"' in htmx.text


async def test_projection_does_not_bypass_csrf_middleware(tmp_path: Path) -> None:
    app = _projected_app(tmp_path, csrf=True)

    async with TestClient(app) as client:
        page = await client.get("/")
        rejected = await client.post(
            "/tasks",
            body=b"title=Bypass&priority=1",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert 'name="_csrf_token"' in page.text
    assert 'toolname="tasks.create"' in page.text
    assert rejected.status == 403


async def test_non_projected_form_keeps_plain_html_fallback(tmp_path: Path) -> None:
    _write_template(tmp_path, projected=False)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/", template="tasks.html")
    def index() -> Page:
        return Page("tasks.html", "form", page_block_name="page_root", errors={})

    async with TestClient(app) as client:
        response = await client.get("/")

    assert 'method="post" action="/tasks"' in response.text
    assert 'type="text" name="title" required' in response.text
    assert "toolname" not in response.text
    assert "toolparamdescription" not in response.text


@pytest.mark.parametrize("control", ["file", "select", "textarea", "checkbox", "radio"])
async def test_unsupported_control_fails_with_actionable_guidance(
    tmp_path: Path,
    control: str,
) -> None:
    @dataclass
    class UploadForm:
        payload: str = field(
            metadata={
                "webmcp_control": control,
                "webmcp_description": "Payload",
            }
        )

    _write_template(tmp_path)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/upload", methods=["POST"])
    @contract(
        form=FormContract(
            UploadForm,
            "tasks.html",
            "form",
            webmcp=WebMCPForm("upload.create", "Upload a payload"),
        )
    )
    def upload() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=rf"unsupported control '{control}'.*Supported"):
        async with TestClient(app):
            pass


async def test_incompatible_constraint_fails_instead_of_silently_degrading(
    tmp_path: Path,
) -> None:
    @dataclass
    class SearchForm:
        query: str = field(
            metadata={
                "webmcp_control": "search",
                "webmcp_description": "Search query",
                "webmcp_min": 1,
            }
        )

    _write_template(tmp_path)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/search")
    @contract(
        form=FormContract(
            SearchForm,
            "tasks.html",
            "form",
            webmcp=WebMCPForm("tasks.create", "Search tasks"),
        )
    )
    def search() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=r"webmcp_min.*do not apply.*search"):
        async with TestClient(app):
            pass


async def test_mutation_autosubmit_is_rejected_before_serving(tmp_path: Path) -> None:
    _write_template(tmp_path)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/tasks", methods=["POST"])
    @contract(
        form=FormContract(
            _TaskForm,
            "tasks.html",
            "form",
            webmcp=WebMCPForm("tasks.create", "Create a task", autosubmit=True),
        )
    )
    def create() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=r"mutation route.*cannot enable autosubmit"):
        async with TestClient(app):
            pass


async def test_projection_helpers_cannot_be_shadowed(tmp_path: Path) -> None:
    _write_template(tmp_path)
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))
    app.template_global("webmcp_form_attrs")(lambda _name: "unsafe")

    @app.route("/tasks", methods=["POST"])
    @contract(
        form=FormContract(
            _TaskForm,
            "tasks.html",
            "form",
            webmcp=WebMCPForm("tasks.create", "Create a task"),
        )
    )
    def create() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=r"reserved.*Remove the custom registration"):
        async with TestClient(app):
            pass


async def test_safe_get_form_may_explicitly_enable_autosubmit(tmp_path: Path) -> None:
    _write_template(tmp_path, tool_name="tasks.search")
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/search", methods=["GET"])
    @contract(
        form=FormContract(
            _TaskForm,
            "tasks.html",
            "form",
            webmcp=WebMCPForm("tasks.search", "Search tasks", autosubmit=True),
        )
    )
    def search() -> Page:
        return Page("tasks.html", "form", page_block_name="page_root", errors={})

    async with TestClient(app) as client:
        response = await client.get("/search")

    assert 'toolname="tasks.search"' in response.text
    assert " toolautosubmit" in response.text

"""WebMCP trust-boundary and invocation-parity proof for issue #576."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import pytest

from chirp import (
    App,
    AppConfig,
    FormAction,
    Page,
    Request,
    ValidationError,
    WebMCPForm,
    form_or_errors,
    login,
    requires,
)
from chirp.contracts import FormContract, check_hypermedia_surface, contract
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.testing import TestClient
from chirp.validation import matches, max_length, required
from tests.helpers.auth import csrf_post, extract_csrf_token, extract_session_cookie

pytestmark = pytest.mark.issue(576)


@dataclass(frozen=True, slots=True)
class _User:
    id: str
    permissions: frozenset[str]
    is_authenticated: bool = True


@dataclass(frozen=True, slots=True)
class _TaskForm:
    title: Annotated[str, required, max_length(40), matches(r"^[^<>]+$")] = field(
        metadata={
            "webmcp_control": "text",
            "webmcp_description": "Task title",
            "webmcp_max_length": 40,
        }
    )


_USERS = {
    "alice": _User("alice", frozenset({"tasks:create"})),
    "bob": _User("bob", frozenset()),
}

_TEMPLATE = """
{% block page_root %}<!doctype html><html><body>
{% block task_form %}
<form id="task-form" method="post" action="/tasks"
      hx-post="/tasks" hx-target="#task-form"
      {{ webmcp_form_attrs("tasks.create") }}>
  {{ csrf_field() }}
  <label>Title <input{{ webmcp_control_attrs("tasks.create", "title") }}></label>
  {% for message in errors | field_errors("title") %}<p>{{ message }}</p>{% end %}
  <button type="submit">Create task (confirm)</button>
</form>
{% end %}
</body></html>{% end %}
"""


def _security_app(tmp_path: Path) -> tuple[App, list[str], dict[str, str]]:
    tmp_path.joinpath("tasks.html").write_text(_TEMPLATE, encoding="utf-8")
    created: list[str] = []
    versions = {"alice": "v1", "bob": "v1"}

    async def load_user(user_id: str) -> _User | None:
        return _USERS.get(user_id)

    def session_version(user: _User) -> str:
        return versions[user.id]

    app = App(AppConfig(template_dir=tmp_path, htmx=True, skip_contract_checks=True))
    app.register_permission("tasks:create")
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(
        AuthMiddleware(
            AuthConfig(
                load_user=load_user,
                session_version=session_version,
            )
        )
    )
    app.add_middleware(CSRFMiddleware())

    form_contract = FormContract(
        _TaskForm,
        "tasks.html",
        "task_form",
        webmcp=WebMCPForm("tasks.create", "Create a task after human confirmation"),
    )

    @app.route("/")
    def index() -> Page:
        return Page("tasks.html", "task_form", page_block_name="page_root", errors={})

    @app.route("/session/{user_id}")
    def start_session(user_id: str) -> str:
        login(_USERS[user_id])
        return "ok"

    @app.route("/tasks", methods=["POST"])
    @contract(form=form_contract)
    @requires("tasks:create")
    async def create_task(request: Request) -> FormAction | ValidationError:
        result = await form_or_errors(request, _TaskForm, "tasks.html", "task_form")
        if isinstance(result, ValidationError):
            return result
        created.append(result.title)
        return FormAction("/", trigger="task-created")

    return app, created, versions


async def _login_cookie(client: TestClient, user_id: str) -> str:
    response = await client.get(f"/session/{user_id}")
    cookie = extract_session_cookie(response)
    assert cookie is not None
    return cookie


async def test_anonymous_and_unauthorized_invocations_cannot_mutate(tmp_path: Path) -> None:
    app, created, _ = _security_app(tmp_path)
    async with TestClient(app) as client:
        anonymous, _ = await csrf_post(
            client,
            "/tasks",
            cookie=None,
            data={"title": "Anonymous"},
            htmx=False,
        )
        bob_cookie = await _login_cookie(client, "bob")
        unauthorized, _ = await csrf_post(
            client,
            "/tasks",
            cookie=bob_cookie,
            data={"title": "Unauthorized"},
            htmx=False,
        )

    assert anonymous.status == 302
    assert unauthorized.status == 403
    assert created == []


async def test_authenticated_full_page_and_htmx_paths_share_authority(
    tmp_path: Path,
) -> None:
    app, created, _ = _security_app(tmp_path)
    async with TestClient(app) as client:
        cookie = await _login_cookie(client, "alice")
        full_page, cookie = await csrf_post(
            client,
            "/tasks",
            cookie=cookie,
            data={"title": "Full page"},
            htmx=False,
        )
        htmx, _ = await csrf_post(
            client,
            "/tasks",
            cookie=cookie,
            data={"title": "Htmx"},
            extra_headers={"HX-Request": "true", "HX-Target": "task-form"},
        )

    assert full_page.status == 303
    assert full_page.header("Location") == "/"
    assert htmx.status == 200
    assert htmx.header("HX-Redirect") == "/"
    assert created == ["Full page", "Htmx"]


async def test_expired_session_and_csrf_failure_stop_before_handler(tmp_path: Path) -> None:
    app, created, versions = _security_app(tmp_path)
    async with TestClient(app) as client:
        cookie = await _login_cookie(client, "alice")
        page = await client.get("/", headers={"Cookie": f"chirp_session={cookie}"})
        token = extract_csrf_token(page.text)
        current_cookie = extract_session_cookie(page) or cookie
        assert token is not None

        versions["alice"] = "v2"
        expired = await client.post(
            "/tasks",
            data={"_csrf_token": token, "title": "Expired"},
            headers={"Cookie": f"chirp_session={current_cookie}"},
        )

        fresh_cookie = await _login_cookie(client, "alice")
        missing_csrf = await client.post(
            "/tasks",
            data={"title": "No CSRF"},
            headers={"Cookie": f"chirp_session={fresh_cookie}"},
        )

    assert expired.status == 302
    assert missing_csrf.status == 403
    assert created == []


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"title": "x" * 41},
        {"title": "<script>alert(1)</script>"},
    ],
)
async def test_malformed_and_adversarial_values_never_call_operation(
    tmp_path: Path,
    data: dict[str, str],
) -> None:
    app, created, _ = _security_app(tmp_path)
    async with TestClient(app) as client:
        cookie = await _login_cookie(client, "alice")
        response, _ = await csrf_post(
            client,
            "/tasks",
            cookie=cookie,
            data=data,
            htmx=False,
        )

    assert response.status == 422
    assert created == []


async def test_mutation_is_discoverable_but_never_auto_submits(tmp_path: Path) -> None:
    app, _, _ = _security_app(tmp_path)
    async with TestClient(app) as client:
        page = await client.get("/")

    assert 'toolname="tasks.create"' in page.text
    assert "toolautosubmit" not in page.text
    assert "Create task (confirm)" in page.text


def test_security_example_has_no_startup_contract_errors(tmp_path: Path) -> None:
    app, _, _ = _security_app(tmp_path)
    app.freeze()

    assert check_hypermedia_surface(app).errors == []

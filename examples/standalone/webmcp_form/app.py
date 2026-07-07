"""Declarative WebMCP attributes on one ordinary typed Chirp form.

Run with ``PYTHONPATH=src python examples/standalone/webmcp_form/app.py``.
The same handler owns human-browser, htmx, and browser-agent submissions.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from chirp import (
    App,
    AppConfig,
    FormAction,
    Page,
    Request,
    ValidationError,
    WebMCPForm,
    form_or_errors,
)
from chirp.contracts import FormContract, contract
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

TEMPLATES = Path(__file__).parent / "templates"
app = App(AppConfig(template_dir=TEMPLATES, htmx=True))
app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")
        )
    )
)
app.add_middleware(CSRFMiddleware())


@dataclass(frozen=True, slots=True)
class TaskForm:
    title: str = field(
        metadata={
            "webmcp_control": "text",
            "webmcp_description": "Short task title",
            "webmcp_min_length": 1,
            "webmcp_max_length": 80,
        }
    )
    priority: int = field(
        default=2,
        metadata={
            "webmcp_control": "number",
            "webmcp_description": "Priority from one to three",
            "webmcp_min": 1,
            "webmcp_max": 3,
        },
    )


TASK_FORM = FormContract(
    TaskForm,
    "tasks.html",
    "task_form",
    webmcp=WebMCPForm("tasks.create", "Create a task"),
)


@app.route("/")
def index() -> Page:
    return Page("tasks.html", "task_form", page_block_name="page_root", errors={})


@app.route("/tasks", methods=["POST"])
@contract(form=TASK_FORM)
async def create_task(request: Request) -> FormAction | ValidationError:
    result = await form_or_errors(request, TaskForm, "tasks.html", "task_form")
    if isinstance(result, ValidationError):
        return result
    return FormAction("/", trigger="task-created")


if __name__ == "__main__":
    app.run()

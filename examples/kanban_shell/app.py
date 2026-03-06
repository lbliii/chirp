"""Kanban Shell — app shell pattern with chirp-ui and mount_pages.

Demonstrates mount_pages + @app.route mix, chirpui-app-shell,
ShellActions, toast, filter sidebar, OOB swaps, and SSE.
"""

import asyncio
import os
import random
from dataclasses import dataclass
from pathlib import Path

from store import (
    COLUMNS,
    Task,  # noqa: F401
    add_task,
    delete_task,
    get_task,
    get_tasks,
    random_move,
    tasks_by_column,
    update_task,
    validate_task,
)

from chirp import (
    OOB,
    App,
    AppConfig,
    EventStream,
    Fragment,
    Redirect,
    Request,
    ValidationError,
    get_user,
    login_required,
    logout,
    use_chirp_ui,
)
from chirp.http.forms import form_or_errors, form_values
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.middleware.static import StaticFiles
from chirp.security.passwords import hash_password

PAGES_DIR = Path(__file__).parent / "pages"
STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


_demo_hash: str | None = None


def _get_demo_hash() -> str:
    global _demo_hash
    if _demo_hash is None:
        _demo_hash = hash_password("password")
    return _demo_hash


_users: dict[str, User] | None = None


def get_users() -> dict[str, User]:
    global _users
    if _users is None:
        h = _get_demo_hash()
        _users = {
            "alice": User(id="alice", name="Alice", password_hash=h),
            "bob": User(id="bob", name="Bob", password_hash=h),
            "carol": User(id="carol", name="Carol", password_hash=h),
        }
    return _users


async def load_user(user_id: str) -> User | None:
    return get_users().get(user_id)


# ---------------------------------------------------------------------------
# Form dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskForm:
    title: str
    description: str = ""
    status: str = "backlog"
    priority: str = "medium"
    assignee: str = ""
    tags: str = ""


@dataclass(frozen=True, slots=True)
class EditTaskForm:
    title: str
    description: str = ""
    priority: str = "medium"
    assignee: str = ""
    tags: str = ""


# ---------------------------------------------------------------------------
# Fragment helpers
# ---------------------------------------------------------------------------


def _column_fragment(column_id: str, tasks: list | None = None) -> Fragment:
    from store import COLUMNS

    if tasks is None:
        tasks = get_tasks()
    column_tasks = [t for t in tasks if t.status == column_id]
    column_name = dict(COLUMNS).get(column_id, column_id)
    return Fragment(
        "page.html",
        "column_block",
        target=f"column-{column_id}",
        column_id=column_id,
        column_name=column_name,
        tasks=column_tasks,
    )


def _stats_fragment(tasks: list | None = None) -> Fragment:
    if tasks is None:
        tasks = get_tasks()
    return Fragment("page.html", "header_stats_oob", target="board-stats", all_tasks=tasks)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=PAGES_DIR)
app = App(config=config)

use_chirp_ui(app)
app.add_middleware(StaticFiles(directory=STATIC_DIR, prefix="/static"))

_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")
app.add_middleware(
    SessionMiddleware(SessionConfig(secret_key=_secret, cookie_name="chirp_session_kanban_shell"))
)
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))

# ---------------------------------------------------------------------------
# API routes (before mount_pages)
# ---------------------------------------------------------------------------


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/login")


@app.route("/tasks", methods=["POST"])
@login_required
async def add_task_route(request: Request):
    result = await form_or_errors(
        request,
        TaskForm,
        "page.html",
        "add_form",
        columns=COLUMNS,
    )
    if isinstance(result, ValidationError):
        return result

    f = result
    assignee = f.assignee or get_user().name
    tags = tuple(t.strip() for t in f.tags.split(",") if t.strip())

    errors = validate_task(f.title, f.status, f.priority)
    if errors:
        return ValidationError(
            "page.html",
            "add_form",
            errors=errors,
            columns=COLUMNS,
            form=form_values(f),
        )

    add_task(f.title, f.description, f.status, f.priority, assignee, tags)
    tasks = get_tasks()
    return OOB(
        _column_fragment(f.status, tasks),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}/edit")
@login_required
def edit_task_route(task_id: int):
    task = get_task(task_id)
    if task is None:
        return ("Task not found", 404)
    return Fragment("task_form.html", "edit_form", task=task)


@app.route("/tasks/{task_id}", methods=["PUT"])
@login_required
async def save_task_route(request: Request, task_id: int):
    task = get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    result = await form_or_errors(
        request,
        EditTaskForm,
        "task_form.html",
        "edit_form",
        task=task,
    )
    if isinstance(result, ValidationError):
        return result

    f = result
    assignee = f.assignee or None
    tags = tuple(t.strip() for t in f.tags.split(",") if t.strip())

    errors = validate_task(f.title, task.status, f.priority)
    if errors:
        return ValidationError(
            "task_form.html",
            "edit_form",
            errors=errors,
            task=task,
        )

    updated = update_task(
        task_id,
        title=f.title,
        description=f.description,
        priority=f.priority,
        assignee=assignee,
        tags=tags,
    )
    if updated is None:
        return ("Task not found", 404)

    tasks = get_tasks()
    return OOB(
        Fragment("page.html", "task_card_block", task=updated, current_user=get_user()),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}/move/{new_status}", methods=["POST"])
@login_required
def move_task_route(task_id: int, new_status: str):
    from store import COLUMN_IDS

    if new_status not in COLUMN_IDS:
        return ("Invalid status", 400)

    task = get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    old_status = task.status
    if new_status == old_status:
        return ("Already in that column", 400)

    update_task(task_id, status=new_status)
    tasks = get_tasks()

    return OOB(
        _column_fragment(old_status, tasks),
        _column_fragment(new_status, tasks),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}", methods=["DELETE"])
@login_required
def delete_task_route(task_id: int):
    task = get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    column = task.status
    delete_task(task_id)
    tasks = get_tasks()

    toast_frag = Fragment(
        "components/toast_oob.html", "toast", message="Task deleted.", variant="info"
    )
    return (
        OOB(
            _column_fragment(column, tasks),
            _stats_fragment(tasks),
            toast_frag,
        ),
        200,
        {"HX-Trigger": "taskDeleted"},
    )


@app.route("/filter")
@login_required
def filter_board_route(request: Request):
    priority_filter = request.query.get_list("priority")
    assignee_filter = request.query.get_list("assignee")
    tag_filter = request.query.get_list("tag")

    tasks = get_tasks()

    if priority_filter:
        tasks = [t for t in tasks if t.priority in priority_filter]
    if assignee_filter:
        tasks = [t for t in tasks if t.assignee in assignee_filter]
    if tag_filter:
        tag_set = set(tag_filter)
        tasks = [t for t in tasks if tag_set & set(t.tags)]

    return Fragment(
        "page.html",
        "board",
        board=tasks_by_column(tasks),
        columns=COLUMNS,
        all_tasks=get_tasks(),
        active_filters={
            "priority": priority_filter,
            "assignee": assignee_filter,
            "tag": tag_filter,
        },
    )


@app.route("/events", referenced=True)
@login_required
def events_route():
    async def generate():
        while True:
            result = random_move()
            if result is not None:
                moved_task, old_status = result
                tasks = get_tasks()
                yield _column_fragment(old_status, tasks)
                yield _column_fragment(moved_task.status, tasks)
                yield _stats_fragment(tasks)
            await asyncio.sleep(random.uniform(1.0, 4.0))

    return EventStream(generate())


# ---------------------------------------------------------------------------
# Mount pages (after API routes)
# ---------------------------------------------------------------------------

app.mount_pages(str(PAGES_DIR))

if __name__ == "__main__":
    app.run()

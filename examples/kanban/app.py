"""Kanban Board — full-featured task board with auth and live updates.

Demonstrates Chirp's htmx ergonomics (OOB multi-fragment swaps, SSE
live updates, inline editing) alongside Kida template features that
aren't showcased in the other examples: pattern matching, optional
chaining, null coalescing, embed, component imports, scoped variables,
fragment caching, and a dozen+ built-in filters.

Auth layer shows how ``SessionMiddleware`` + ``AuthMiddleware`` compose
with everything else.  Three demo accounts (Alice, Bob, Carol) share a
single board — the logged-in user's cards are highlighted.

Demonstrates:
- ``SessionMiddleware`` + ``AuthMiddleware`` setup
- ``login()`` / ``logout()`` helpers with ``@login_required``
- ``current_user()`` template global for identity-aware rendering
- ``OOB`` for multi-target updates (source column + dest column + stats)
- ``EventStream`` with simulated live activity from "other users"
- ``Fragment`` / ``Page`` for full-page vs partial rendering
- ``ValidationError`` for 422 form errors
- Thread-safe in-memory storage with ``threading.Lock``
- Kida component templates with ``{% from ... import %}``, ``{% embed %}``,
  ``{% match %}``, ``{% def %}``, ``{{ ?.  }}``, ``{{ ?? }}``, and more

Run:
    python app.py
"""

import asyncio
import random
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    OOB,
    Page,
    Redirect,
    Request,
    Template,
    ValidationError,
    get_user,
    is_safe_url,
    login,
    login_required,
    logout,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.security.passwords import hash_password, verify_password

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# User model + in-memory "database"
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class User:
    """Minimal user model — satisfies chirp's User protocol."""

    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


# Pre-hash the demo password so verify_password works correctly
_DEMO_HASH = hash_password("password")

USERS: dict[str, User] = {
    "alice": User(id="alice", name="Alice", password_hash=_DEMO_HASH),
    "bob": User(id="bob", name="Bob", password_hash=_DEMO_HASH),
    "carol": User(id="carol", name="Carol", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    """Load a user by ID — called by AuthMiddleware on each request."""
    return USERS.get(user_id)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

app.add_middleware(SessionMiddleware(SessionConfig(secret_key="kanban-demo-secret")))
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

COLUMNS: list[tuple[str, str]] = [
    ("backlog", "Backlog"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("done", "Done"),
]

COLUMN_IDS: set[str] = {col_id for col_id, _ in COLUMNS}

# Adjacent columns for move validation
_ADJACENT: dict[str, list[str]] = {
    "backlog": ["in_progress"],
    "in_progress": ["backlog", "review"],
    "review": ["in_progress", "done"],
    "done": ["review"],
}

PRIORITIES: list[str] = ["high", "medium", "low"]

# ---------------------------------------------------------------------------
# Data model — frozen for free-threading safety
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    title: str
    description: str
    status: str
    priority: str
    assignee: str | None
    tags: tuple[str, ...]
    created_at: str


# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_tasks: list[Task] = []
_lock = threading.Lock()
_next_id = 1

_SEED: list[dict] = [
    {
        "title": "Design landing page",
        "description": "Create mockups for the new marketing site with responsive layouts",
        "status": "done",
        "priority": "high",
        "assignee": "Alice",
        "tags": ("design", "frontend"),
    },
    {
        "title": "Set up CI pipeline",
        "description": "Configure GitHub Actions for test, lint, and deploy stages",
        "status": "done",
        "priority": "medium",
        "assignee": "Bob",
        "tags": ("devops",),
    },
    {
        "title": "Implement auth flow",
        "description": "Session-based login with password hashing and CSRF protection",
        "status": "review",
        "priority": "high",
        "assignee": "Carol",
        "tags": ("backend", "security"),
    },
    {
        "title": "Write API docs",
        "description": "Document all public endpoints with request/response examples",
        "status": "review",
        "priority": "medium",
        "assignee": None,
        "tags": ("docs",),
    },
    {
        "title": "Add search indexing",
        "description": "Full-text search across content using SQLite FTS5",
        "status": "in_progress",
        "priority": "high",
        "assignee": "Alice",
        "tags": ("backend", "search"),
    },
    {
        "title": "Dashboard charts",
        "description": "Render analytics charts with server-side SVG generation",
        "status": "in_progress",
        "priority": "medium",
        "assignee": "Bob",
        "tags": ("frontend", "analytics"),
    },
    {
        "title": "Rate limiting middleware",
        "description": "Token bucket rate limiter for API endpoints",
        "status": "backlog",
        "priority": "medium",
        "assignee": "Carol",
        "tags": ("backend", "security"),
    },
    {
        "title": "Dark mode toggle",
        "description": "CSS custom properties with localStorage persistence and OS preference detection",
        "status": "backlog",
        "priority": "low",
        "assignee": None,
        "tags": ("frontend", "design"),
    },
    {
        "title": "Database migrations",
        "description": "Schema versioning with forward and rollback support",
        "status": "backlog",
        "priority": "high",
        "assignee": None,
        "tags": ("backend", "devops"),
    },
    {
        "title": "Performance profiling",
        "description": "Identify bottlenecks in the rendering pipeline under load",
        "status": "backlog",
        "priority": "low",
        "assignee": "Alice",
        "tags": ("backend",),
    },
]


def _seed() -> None:
    global _next_id
    with _lock:
        now = datetime.now(UTC)
        for i, data in enumerate(_SEED):
            _tasks.append(
                Task(
                    id=_next_id,
                    title=data["title"],
                    description=data["description"],
                    status=data["status"],
                    priority=data["priority"],
                    assignee=data["assignee"],
                    tags=data["tags"],
                    created_at=(now.replace(minute=i * 5 % 60)).strftime("%H:%M"),
                )
            )
            _next_id += 1


_seed()


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _get_tasks() -> list[Task]:
    with _lock:
        return list(_tasks)


def _get_task(task_id: int) -> Task | None:
    with _lock:
        for t in _tasks:
            if t.id == task_id:
                return t
        return None


def _add_task(
    title: str,
    description: str,
    status: str,
    priority: str,
    assignee: str | None,
    tags: tuple[str, ...],
) -> Task:
    global _next_id
    with _lock:
        task = Task(
            id=_next_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            tags=tags,
            created_at=datetime.now(UTC).strftime("%H:%M"),
        )
        _next_id += 1
        _tasks.append(task)
        return task


def _update_task(task_id: int, **fields: str | None | tuple[str, ...]) -> Task | None:
    with _lock:
        for i, t in enumerate(_tasks):
            if t.id == task_id:
                updated = replace(t, **fields)
                _tasks[i] = updated
                return updated
        return None


def _delete_task(task_id: int) -> bool:
    with _lock:
        before = len(_tasks)
        _tasks[:] = [t for t in _tasks if t.id != task_id]
        return len(_tasks) < before


def _tasks_by_column(tasks: list[Task] | None = None) -> dict[str, list[Task]]:
    """Group tasks into columns. Returns a dict with all column IDs as keys."""
    if tasks is None:
        tasks = _get_tasks()
    board: dict[str, list[Task]] = {col_id: [] for col_id, _ in COLUMNS}
    for task in tasks:
        board.setdefault(task.status, []).append(task)
    return board


def _random_move() -> tuple[Task, str] | None:
    """Pick a random task and move it to an adjacent column. Returns (task, old_status)."""
    with _lock:
        if not _tasks:
            return None
        task = random.choice(_tasks)
        adjacent = _ADJACENT.get(task.status, [])
        if not adjacent:
            return None
        new_status = random.choice(adjacent)
        old_status = task.status
        updated = replace(task, status=new_status)
        idx = _tasks.index(task)
        _tasks[idx] = updated
        return (updated, old_status)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_task(title: str, status: str, priority: str) -> dict[str, list[str]]:
    """Validate task fields. Returns a dict of errors (empty = valid)."""
    errors: dict[str, list[str]] = {}
    if not title.strip():
        errors.setdefault("title", []).append("Title is required.")
    elif len(title) > 200:
        errors.setdefault("title", []).append("Title must be 200 characters or less.")
    if status not in COLUMN_IDS:
        errors.setdefault("status", []).append(f"Invalid status: {status}")
    if priority not in PRIORITIES:
        errors.setdefault("priority", []).append(f"Invalid priority: {priority}")
    return errors


# ---------------------------------------------------------------------------
# Shared context helpers
# ---------------------------------------------------------------------------


def _board_context(tasks: list[Task] | None = None) -> dict:
    """Build the standard context for board rendering."""
    if tasks is None:
        tasks = _get_tasks()
    return {
        "board": _tasks_by_column(tasks),
        "columns": COLUMNS,
        "all_tasks": tasks,
        "active_filters": {"priority": [], "assignee": [], "tag": []},
    }


def _column_fragment(column_id: str, tasks: list[Task] | None = None) -> Fragment:
    """Render a single column fragment for OOB swaps."""
    if tasks is None:
        tasks = _get_tasks()
    column_tasks = [t for t in tasks if t.status == column_id]
    column_name = dict(COLUMNS).get(column_id, column_id)
    return Fragment(
        "board.html",
        "column_block",
        column_id=column_id,
        column_name=column_name,
        tasks=column_tasks,
    )


def _stats_fragment(tasks: list[Task] | None = None) -> Fragment:
    """Render the stats bar fragment for OOB swaps."""
    if tasks is None:
        tasks = _get_tasks()
    return Fragment("board.html", "header_stats", all_tasks=tasks)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.route("/login")
def login_page():
    """Show the login form."""
    return Template("login.html", error="", users=USERS)


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    """Handle login form submission."""
    form = await request.form()
    username = form.get("username", "").strip().lower()
    password = form.get("password", "")

    user = USERS.get(username)
    if user and verify_password(password, user.password_hash):
        login(user)
        next_url = request.query.get("next", "/")
        if not is_safe_url(next_url):
            next_url = "/"
        return Redirect(next_url)

    return Template("login.html", error="Invalid username or password", users=USERS)


@app.route("/logout", methods=["POST"])
def do_logout():
    """Log out and redirect to login."""
    logout()
    return Redirect("/login")


# ---------------------------------------------------------------------------
# Board routes (all protected)
# ---------------------------------------------------------------------------


@app.route("/")
@login_required
def index(request: Request):
    """Full board page or board fragment depending on htmx request."""
    ctx = _board_context()
    return Page("board.html", "board", **ctx)


@app.route("/tasks", methods=["POST"])
@login_required
async def add_task(request: Request):
    """Add a task — returns OOB (column + stats) or ValidationError."""
    form = await request.form()
    title = form.get("title", "")
    description = form.get("description", "")
    status = form.get("status", "backlog")
    priority = form.get("priority", "medium")
    assignee = form.get("assignee", "").strip() or get_user().name
    raw_tags = form.get("tags", "")
    tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())

    errors = _validate_task(title, status, priority)
    if errors:
        return ValidationError(
            "board.html",
            "add_form",
            errors=errors,
            columns=COLUMNS,
            form={"title": title, "description": description, "status": status,
                  "priority": priority, "assignee": assignee or "", "tags": raw_tags},
        )

    _add_task(title, description, status, priority, assignee, tags)
    tasks = _get_tasks()
    return OOB(
        _column_fragment(status, tasks),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}/edit")
@login_required
def edit_task(task_id: int):
    """Return the inline edit form for a task card."""
    task = _get_task(task_id)
    if task is None:
        return ("Task not found", 404)
    return Fragment("task_form.html", "edit_form", task=task)


@app.route("/tasks/{task_id}", methods=["PUT"])
@login_required
async def save_task(request: Request, task_id: int):
    """Save an edited task — returns OOB (card + stats) or ValidationError."""
    form = await request.form()
    title = form.get("title", "")
    description = form.get("description", "")
    priority = form.get("priority", "medium")
    assignee = form.get("assignee", "").strip() or None
    raw_tags = form.get("tags", "")
    tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())

    task = _get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    errors = _validate_task(title, task.status, priority)
    if errors:
        return ValidationError(
            "task_form.html",
            "edit_form",
            errors=errors,
            task=task,
        )

    updated = _update_task(
        task_id,
        title=title,
        description=description,
        priority=priority,
        assignee=assignee,
        tags=tags,
    )
    if updated is None:
        return ("Task not found", 404)

    tasks = _get_tasks()
    return OOB(
        Fragment("board.html", "task_card_block", task=updated),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}/move/{new_status}", methods=["POST"])
@login_required
def move_task(task_id: int, new_status: str):
    """Move a task to a different column — returns OOB for both columns + stats."""
    if new_status not in COLUMN_IDS:
        return ("Invalid status", 400)

    task = _get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    old_status = task.status
    if new_status == old_status:
        return ("Already in that column", 400)

    _update_task(task_id, status=new_status)
    tasks = _get_tasks()

    return OOB(
        _column_fragment(old_status, tasks),
        _column_fragment(new_status, tasks),
        _stats_fragment(tasks),
    )


@app.route("/tasks/{task_id}", methods=["DELETE"])
@login_required
def delete_task_route(task_id: int):
    """Delete a task — returns updated column + stats with HX-Trigger."""
    task = _get_task(task_id)
    if task is None:
        return ("Task not found", 404)

    column = task.status
    _delete_task(task_id)
    tasks = _get_tasks()

    return (
        OOB(
            _column_fragment(column, tasks),
            _stats_fragment(tasks),
        ),
        200,
        {"HX-Trigger": "taskDeleted"},
    )


@app.route("/filter")
@login_required
def filter_board(request: Request):
    """Filter the board by priority, assignee, or tag."""
    priority_filter = request.query.get_list("priority")
    assignee_filter = request.query.get_list("assignee")
    tag_filter = request.query.get_list("tag")

    tasks = _get_tasks()

    if priority_filter:
        tasks = [t for t in tasks if t.priority in priority_filter]
    if assignee_filter:
        tasks = [t for t in tasks if t.assignee in assignee_filter]
    if tag_filter:
        tag_set = set(tag_filter)
        tasks = [t for t in tasks if tag_set & set(t.tags)]

    return Fragment(
        "board.html",
        "board",
        board=_tasks_by_column(tasks),
        columns=COLUMNS,
        all_tasks=_get_tasks(),
        active_filters={
            "priority": priority_filter,
            "assignee": assignee_filter,
            "tag": tag_filter,
        },
    )


@app.route("/events")
@login_required
def events():
    """SSE endpoint — simulates live task movement from other users.

    Every few seconds, picks a random task and moves it to an adjacent
    column. Pushes OOB fragments for both affected columns and the
    stats bar, just like user-initiated moves.
    """

    async def generate():
        while True:
            result = _random_move()
            if result is not None:
                moved_task, old_status = result
                tasks = _get_tasks()

                yield _column_fragment(old_status, tasks)
                yield _column_fragment(moved_task.status, tasks)
                yield _stats_fragment(tasks)

            # Staggered updates: 1-4s between ticks
            await asyncio.sleep(random.uniform(1.0, 4.0))

    return EventStream(generate())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run()

"""Shared data model and storage for kanban_shell.

Used by app.py and pages/ handlers. Thread-safe in-memory storage.
"""

import random
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime

COLUMNS: list[tuple[str, str]] = [
    ("backlog", "Backlog"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("done", "Done"),
]

COLUMN_IDS: set[str] = {col_id for col_id, _ in COLUMNS}

_ADJACENT: dict[str, list[str]] = {
    "backlog": ["in_progress"],
    "in_progress": ["backlog", "review"],
    "review": ["in_progress", "done"],
    "done": ["review"],
}

PRIORITIES: list[str] = ["high", "medium", "low"]


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


_tasks: list[Task] = []
_lock = threading.Lock()
_next_id = 1

_SEED: list[dict] = [
    {"title": "Design landing page", "description": "Create mockups", "status": "done", "priority": "high", "assignee": "Alice", "tags": ("design", "frontend")},
    {"title": "Set up CI pipeline", "description": "Configure GitHub Actions", "status": "done", "priority": "medium", "assignee": "Bob", "tags": ("devops",)},
    {"title": "Implement auth flow", "description": "Session-based login", "status": "review", "priority": "high", "assignee": "Carol", "tags": ("backend", "security")},
    {"title": "Write API docs", "description": "Document endpoints", "status": "review", "priority": "medium", "assignee": None, "tags": ("docs",)},
    {"title": "Add search indexing", "description": "Full-text search", "status": "in_progress", "priority": "high", "assignee": "Alice", "tags": ("backend", "search")},
    {"title": "Dashboard charts", "description": "Analytics charts", "status": "in_progress", "priority": "medium", "assignee": "Bob", "tags": ("frontend", "analytics")},
    {"title": "Rate limiting middleware", "description": "Token bucket", "status": "backlog", "priority": "medium", "assignee": "Carol", "tags": ("backend", "security")},
    {"title": "Dark mode toggle", "description": "CSS custom properties", "status": "backlog", "priority": "low", "assignee": None, "tags": ("frontend", "design")},
    {"title": "Database migrations", "description": "Schema versioning", "status": "backlog", "priority": "high", "assignee": None, "tags": ("backend", "devops")},
    {"title": "Performance profiling", "description": "Identify bottlenecks", "status": "backlog", "priority": "low", "assignee": "Alice", "tags": ("backend",)},
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


def get_tasks() -> list[Task]:
    with _lock:
        return list(_tasks)


def get_task(task_id: int) -> Task | None:
    with _lock:
        for t in _tasks:
            if t.id == task_id:
                return t
        return None


def add_task(
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


def update_task(task_id: int, **fields: str | None | tuple[str, ...]) -> Task | None:
    with _lock:
        for i, t in enumerate(_tasks):
            if t.id == task_id:
                updated = replace(t, **fields)
                _tasks[i] = updated
                return updated
        return None


def delete_task(task_id: int) -> bool:
    with _lock:
        before = len(_tasks)
        _tasks[:] = [t for t in _tasks if t.id != task_id]
        return len(_tasks) < before


def tasks_by_column(tasks: list[Task] | None = None) -> dict[str, list[Task]]:
    if tasks is None:
        tasks = get_tasks()
    board: dict[str, list[Task]] = {col_id: [] for col_id, _ in COLUMNS}
    for task in tasks:
        board.setdefault(task.status, []).append(task)
    return board


def random_move() -> tuple[Task, str] | None:
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


def validate_task(title: str, status: str, priority: str) -> dict[str, list[str]]:
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

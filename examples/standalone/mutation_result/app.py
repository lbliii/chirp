"""MutationResult — progressive enhancement for all mutations.

Demonstrates how a single handler serves three UX flows:
- htmx + fragments: renders OOB fragments (fast, no page reload)
- htmx + no fragments: sends HX-Redirect (client-side full redirect)
- non-htmx: 303 server redirect (plain HTML forms work too)

Shows POST (add), DELETE (remove), and PATCH (toggle) — all using MutationResult.

Run:
    python app.py
"""

import threading
from pathlib import Path

from chirp import App, AppConfig, Fragment, MutationResult, Page, Request

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)

# ---------------------------------------------------------------------------
# In-memory task store — thread-safe for free-threading
# ---------------------------------------------------------------------------

_tasks: list[dict] = [
    {"id": 1, "text": "Buy groceries", "done": False},
    {"id": 2, "text": "Write docs", "done": True},
    {"id": 3, "text": "Review PR", "done": False},
]
_lock = threading.Lock()
_next_id = 4


def _get_tasks() -> list[dict]:
    with _lock:
        return list(_tasks)


def _add_task(text: str) -> dict:
    global _next_id
    with _lock:
        task = {"id": _next_id, "text": text, "done": False}
        _next_id += 1
        _tasks.append(task)
        return task


def _delete_task(task_id: int) -> bool:
    with _lock:
        for i, task in enumerate(_tasks):
            if task["id"] == task_id:
                _tasks.pop(i)
                return True
        return False


def _toggle_task(task_id: int) -> dict | None:
    with _lock:
        for task in _tasks:
            if task["id"] == task_id:
                task["done"] = not task["done"]
                return dict(task)
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    tasks = _get_tasks()
    return Page("tasks.html", "task_list", tasks=tasks, count=len(tasks))


@app.route("/tasks", methods=["POST"])
async def add_task(request: Request):
    """Add a task — htmx gets updated list + count, plain POST gets redirect."""
    form = await request.form()
    text = (form.get("text") or "").strip()
    if text:
        _add_task(text)
    tasks = _get_tasks()
    return MutationResult(
        "/",
        Fragment("tasks.html", "task_list", tasks=tasks, count=len(tasks)),
        Fragment("tasks.html", "task_count", target="task-count", count=len(tasks)),
        trigger="taskAdded",
    )


@app.route("/tasks/{task_id}", methods=["DELETE"])
def delete_task(task_id: int):
    """Delete a task — htmx gets updated list, plain request gets redirect."""
    _delete_task(task_id)
    tasks = _get_tasks()
    return MutationResult(
        "/",
        Fragment("tasks.html", "task_list", tasks=tasks, count=len(tasks)),
        Fragment("tasks.html", "task_count", target="task-count", count=len(tasks)),
        trigger="taskDeleted",
    )


@app.route("/tasks/{task_id}/toggle", methods=["PATCH"])
def toggle_task(task_id: int):
    """Toggle done/undone — htmx gets updated list, plain request gets redirect."""
    _toggle_task(task_id)
    tasks = _get_tasks()
    return MutationResult(
        "/",
        Fragment("tasks.html", "task_list", tasks=tasks, count=len(tasks)),
    )


if __name__ == "__main__":
    app.run()

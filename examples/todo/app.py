"""Todo List — htmx fragments with chirp.

Demonstrates the killer feature: same template renders as a full page
or a fragment, depending on whether the request came from htmx.

Run:
    python app.py
"""

import threading
from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, Template, ValidationError

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_todos: list[dict] = []
_lock = threading.Lock()
_next_id = 1


def _get_todos() -> list[dict]:
    with _lock:
        return list(_todos)


def _add_todo(text: str) -> dict:
    global _next_id
    with _lock:
        todo = {"id": _next_id, "text": text, "done": False}
        _next_id += 1
        _todos.append(todo)
        return todo


def _toggle_todo(todo_id: int) -> None:
    with _lock:
        for todo in _todos:
            if todo["id"] == todo_id:
                todo["done"] = not todo["done"]
                return


def _delete_todo(todo_id: int) -> None:
    with _lock:
        _todos[:] = [t for t in _todos if t["id"] != todo_id]


# ---------------------------------------------------------------------------
# Template filter
# ---------------------------------------------------------------------------


@app.template_filter("completed_class")
def completed_class(todo: dict) -> str:
    """Return a CSS class name based on completion state."""
    return "done" if todo.get("done") else ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index(request: Request):
    """Full page or fragment depending on htmx request."""
    todos = _get_todos()
    if request.is_fragment:
        return Fragment("index.html", "todo_list", todos=todos)
    return Template("index.html", todos=todos)


@app.route("/todos", methods=["POST"])
async def add_todo(request: Request):
    """Add a todo item — returns the list fragment or a 422 validation error."""
    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        return ValidationError(
            "index.html", "todo_list",
            error="Todo text is required",
            todos=_get_todos(),
        )
    _add_todo(text)
    return Fragment("index.html", "todo_list", todos=_get_todos())


@app.route("/todos/{todo_id}/toggle", methods=["POST"])
def toggle_todo(todo_id: int):
    """Toggle a todo's completion state — returns the list fragment."""
    _toggle_todo(todo_id)
    todos = _get_todos()
    return Fragment("index.html", "todo_list", todos=todos)


@app.route("/todos/{todo_id}", methods=["DELETE"])
def delete_todo(todo_id: int):
    """Delete a todo — returns the list fragment."""
    _delete_todo(todo_id)
    todos = _get_todos()
    return Fragment("index.html", "todo_list", todos=todos)


if __name__ == "__main__":
    app.run()

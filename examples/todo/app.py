"""Todo List — htmx fragments with chirp.data persistence.

Demonstrates two killer features together:
1. Same template renders as a full page or a fragment (htmx)
2. SQL in, frozen dataclasses out (chirp.data)

Add todos, restart the server, and they're still there.

Run:
    pip install chirp[data]
    python app.py
"""

import os
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, Template, ValidationError
from chirp.data import Query
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(os.environ.get("CHIRP_TODO_DB", str(Path(__file__).parent / "todo.db")))

# ---------------------------------------------------------------------------
# Data model — frozen dataclass, same object from DB through to template
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    text: str
    done: bool


# Reusable query — immutable, so safe to define once at module level
ALL_TODOS = Query(Todo, "todos").order_by("id")

# ---------------------------------------------------------------------------
# App — database connects at startup, migrations run automatically
# ---------------------------------------------------------------------------

app = App(
    config=AppConfig(template_dir=TEMPLATES_DIR),
    db=f"sqlite:///{DB_PATH}",
    migrations=str(MIGRATIONS_DIR),
)
_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")

app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))
app.add_middleware(CSRFMiddleware())

# No custom filter needed — using inline ternary in the template instead:
#   class="{{ 'done' if todo.done else '' }}"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index(request: Request):
    """Full page or fragment depending on htmx request."""
    todos = await ALL_TODOS.fetch(app.db)
    if request.is_fragment:
        return Fragment("index.html", "todo_list", todos=todos)
    return Template("index.html", todos=todos)


@app.route("/todos", methods=["POST"])
async def add_todo(request: Request):
    """Add a todo item — returns the list fragment or a 422 validation error."""
    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        todos = await ALL_TODOS.fetch(app.db)
        return ValidationError(
            "index.html",
            "todo_list",
            error="Todo text is required",
            todos=todos,
        )
    await app.db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", text, False)
    todos = await ALL_TODOS.fetch(app.db)
    return Fragment("index.html", "todo_list", todos=todos)


@app.route("/todos/{todo_id}/toggle", methods=["POST"])
async def toggle_todo(todo_id: int):
    """Toggle a todo's completion state — returns the list fragment."""
    await app.db.execute("UPDATE todos SET done = NOT done WHERE id = ?", todo_id)
    todos = await ALL_TODOS.fetch(app.db)
    return Fragment("index.html", "todo_list", todos=todos)


@app.route("/todos/{todo_id}", methods=["DELETE"])
async def delete_todo(todo_id: int):
    """Delete a todo — returns the list fragment."""
    await app.db.execute("DELETE FROM todos WHERE id = ?", todo_id)
    todos = await ALL_TODOS.fetch(app.db)
    return Fragment("index.html", "todo_list", todos=todos)


if __name__ == "__main__":
    app.run()

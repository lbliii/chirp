"""Todo List — htmx fragments with chirp.data persistence.

Demonstrates two killer features together:
1. Same template renders as a full page or a fragment (htmx)
2. SQL in, frozen dataclasses out (chirp.data)

Add todos, restart the server, and they're still there.

Run:
    pip install chirp[data]
    python app.py
"""

from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, Template, ValidationError
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(__file__).parent / "todo.db"

# ---------------------------------------------------------------------------
# Data model — frozen dataclass, same object from DB through to template
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    text: str
    done: bool


# ---------------------------------------------------------------------------
# App — database connects at startup, migrations run automatically
# ---------------------------------------------------------------------------

app = App(
    config=AppConfig(template_dir=TEMPLATES_DIR),
    db=f"sqlite:///{DB_PATH}",
    migrations=str(MIGRATIONS_DIR),
)
app.add_middleware(SessionMiddleware(SessionConfig(secret_key="todo-demo-secret")))
app.add_middleware(CSRFMiddleware())

# No custom filter needed — using inline ternary in the template instead:
#   class="{{ 'done' if todo.done else '' }}"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index(request: Request):
    """Full page or fragment depending on htmx request."""
    todos = await app.db.fetch(Todo, "SELECT * FROM todos ORDER BY id")
    if request.is_fragment:
        return Fragment("index.html", "todo_list", todos=todos)
    return Template("index.html", todos=todos)


@app.route("/todos", methods=["POST"])
async def add_todo(request: Request):
    """Add a todo item — returns the list fragment or a 422 validation error."""
    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        todos = await app.db.fetch(Todo, "SELECT * FROM todos ORDER BY id")
        return ValidationError(
            "index.html",
            "todo_list",
            error="Todo text is required",
            todos=todos,
        )
    await app.db.execute("INSERT INTO todos (text, done) VALUES (?, ?)", text, False)
    todos = await app.db.fetch(Todo, "SELECT * FROM todos ORDER BY id")
    return Fragment("index.html", "todo_list", todos=todos)


@app.route("/todos/{todo_id}/toggle", methods=["POST"])
async def toggle_todo(todo_id: int):
    """Toggle a todo's completion state — returns the list fragment."""
    await app.db.execute(
        "UPDATE todos SET done = NOT done WHERE id = ?", todo_id
    )
    todos = await app.db.fetch(Todo, "SELECT * FROM todos ORDER BY id")
    return Fragment("index.html", "todo_list", todos=todos)


@app.route("/todos/{todo_id}", methods=["DELETE"])
async def delete_todo(todo_id: int):
    """Delete a todo — returns the list fragment."""
    await app.db.execute("DELETE FROM todos WHERE id = ?", todo_id)
    todos = await app.db.fetch(Todo, "SELECT * FROM todos ORDER BY id")
    return Fragment("index.html", "todo_list", todos=todos)


if __name__ == "__main__":
    app.run()

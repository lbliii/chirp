"""Reactive Task Board — live updates via ReactiveBus + SSE.

Demonstrates Chirp's reactive system: when one browser tab mutates data,
all other connected tabs update automatically via Server-Sent Events.
No polling. No client-side JavaScript beyond htmx.

Three reactive blocks update in real time:
  - task_list:   the full list of tasks
  - task_count:  a badge showing the total count
  - last_update: a timestamp of the most recent change

Run:
    python app.py

Then open two browser tabs to the same URL and add/toggle tasks in one
— the other tab updates within a second.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, Template, ValidationError
from chirp.pages.reactive import BlockRef, ChangeEvent, DependencyIndex, ReactiveBus
from chirp.pages.reactive.stream import reactive_stream

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    title: str
    done: bool = False


# ---------------------------------------------------------------------------
# Thread-safe in-memory store
# ---------------------------------------------------------------------------


class TaskStore:
    """Simple thread-safe task store backed by a list."""

    __slots__ = ("_lock", "_next_id", "_tasks")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[Task] = [
            Task(id=1, title="Try the reactive demo", done=False),
            Task(id=2, title="Open a second tab", done=False),
            Task(id=3, title="Watch it update", done=False),
        ]
        self._next_id = 4

    def all(self) -> list[Task]:
        with self._lock:
            return list(self._tasks)

    def add(self, title: str) -> Task:
        with self._lock:
            task = Task(id=self._next_id, title=title)
            self._next_id += 1
            self._tasks.append(task)
            return task

    def toggle(self, task_id: int) -> Task | None:
        with self._lock:
            for i, t in enumerate(self._tasks):
                if t.id == task_id:
                    toggled = Task(id=t.id, title=t.title, done=not t.done)
                    self._tasks[i] = toggled
                    return toggled
        return None

    def delete(self, task_id: int) -> bool:
        with self._lock:
            before = len(self._tasks)
            self._tasks = [t for t in self._tasks if t.id != task_id]
            return len(self._tasks) < before


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

store = TaskStore()
bus = ReactiveBus()

# Dependency index: maps context paths to template blocks.
dep_index = DependencyIndex()
for block_name in ("task_list", "task_count", "last_update"):
    dep_index.register("tasks", BlockRef(template_name="board.html", block_name=block_name))


config = AppConfig(
    template_dir=TEMPLATES_DIR,
    worker_mode="async",
    sse_close_event="close",
)
app = App(config=config)

_last_update = ""


def _context() -> dict:
    """Build the current context for reactive re-renders."""
    return {
        "tasks": store.all(),
        "count": len(store.all()),
        "last_update": _last_update,
    }


def _notify(origin: str | None = None) -> None:
    """Emit a change event after a mutation."""
    global _last_update
    _last_update = time.strftime("%H:%M:%S")
    bus.emit_sync(
        ChangeEvent(
            scope="board",
            changed_paths=frozenset({"tasks"}),
            origin=origin,
        )
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Full page render."""
    return Template("board.html", **_context())


@app.route("/tasks", methods=["POST"], name="tasks.add")
async def add_task(request: Request):
    """Add a task and notify all connected clients."""
    form = await request.form()
    title = (form.get("title") or "").strip()
    if not title:
        return ValidationError(
            "board.html",
            "task_list",
            error="Title is required",
            **_context(),
        )
    store.add(title)
    _notify()
    return Fragment("board.html", "task_list", **_context())


@app.route("/tasks/{task_id}/toggle", methods=["POST"], name="tasks.toggle")
def toggle_task(task_id: int):
    """Toggle a task's done state."""
    store.toggle(task_id)
    _notify()
    return Fragment("board.html", "task_list", **_context())


@app.route("/tasks/{task_id}", methods=["DELETE"], name="tasks.delete")
def delete_task(task_id: int):
    """Delete a task."""
    store.delete(task_id)
    _notify()
    return Fragment("board.html", "task_list", **_context())


@app.route("/events", referenced=True)
def events():
    """SSE stream — auto-pushes reactive block updates."""
    return reactive_stream(
        bus,
        scope="board",
        index=dep_index,
        context_builder=_context,
    )


if __name__ == "__main__":
    app.run()

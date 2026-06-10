"""Shapes — the verified, multi-tenant data layer.

A tiny multi-tenant project tracker (workspaces → projects → tasks → comments)
that shows off what `chirp.data` Shapes give you that an ORM or a hand-rolled
query layer does not:

1. **A verified SQL→render contract.** Each block declares the exact `SELECT`
   that feeds it, co-located with a frozen dataclass. `app.check()` proves at
   startup that the template reads only fields the query actually fetched — so a
   renamed column is a *startup error*, not a silent `None` a user discovers.

2. **Tenant isolation you cannot forget.** Every Shape declares
   `scope="workspace_id"`. The predicate is *structurally injected* into the
   parent query and every batched child query — there is no hand-written
   `WHERE workspace_id = ...` to omit, and omitting `scope=` fails loud.

3. **No N+1.** The dashboard's projects → tasks → comments load in a *bounded*
   number of queries (one batched query per level), independent of row count —
   not one query per project and one per task.

Run:
    uv run python examples/standalone/shapes_workspaces/app.py

Then open http://localhost:8000 — you are "logged in" to workspace 1 (Acme).
Globex's data (workspace 2) is in the same tables but can never appear.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Page, Request, Template
from chirp.data import Composite, Shape, composite, nested, shape

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(os.environ.get("CHIRP_WORKSPACES_DB", str(Path(__file__).parent / "workspaces.db")))

# In a real app this is a server-side fact — `request.user.workspace_id` from the
# authenticated session. NEVER trust a client-supplied tenant id: that is the
# whole point of `scope=`. We hardcode "you are workspace 1" for the demo.
CURRENT_WORKSPACE_ID = 1


# ---------------------------------------------------------------------------
# Shapes — SQL in, frozen dataclasses out, verified against the templates
# ---------------------------------------------------------------------------


@shape("SELECT id, name FROM workspaces WHERE id = :id")
@dataclass(frozen=True, slots=True)
class Workspace:
    """The tenant itself (the workspaces table is not tenant-scoped)."""

    id: int
    name: str


@shape(
    "SELECT id, task_id, author, body FROM comments "
    "WHERE task_id = :task_id "
    "ORDER BY created_at DESC LIMIT 3",
    scope="workspace_id",
)
@dataclass(frozen=True, slots=True)
class Comment:
    # `ORDER BY ... LIMIT 3` is preserved per-parent: each task gets its own three
    # most-recent comments compiled into a single batched window query, not "all
    # comments, arbitrary order" and not one query per task.
    id: int
    task_id: int
    author: str
    body: str


@shape(
    "SELECT id, project_id, title, priority, done FROM tasks "
    "WHERE project_id = :project_id "
    "ORDER BY priority DESC, id",
    scope="workspace_id",
)
@dataclass(frozen=True, slots=True)
class Task:
    id: int
    project_id: int
    title: str
    priority: int
    done: bool
    # Nested children carry their own SQL and batch with the parent.
    comments: tuple[Comment, ...] = nested(Comment, on="task_id", key="id")


@shape("SELECT id, name, status FROM projects ORDER BY id", scope="workspace_id")
@dataclass(frozen=True, slots=True)
class Project:
    # No `WHERE workspace_id = ...` here — `scope=` injects it. Listing "my
    # projects" is just `Shape.fetch(Project, db, scope=my_workspace)`.
    id: int
    name: str
    status: str
    tasks: tuple[Task, ...] = nested(Task, on="project_id", key="id")


@shape(
    "SELECT id, project_id, title, priority FROM tasks ORDER BY created_at DESC LIMIT 5",
    scope="workspace_id",
)
@dataclass(frozen=True, slots=True)
class RecentTask:
    """A flat 'recent activity' feed — top-level fetch, globally limited."""

    id: int
    project_id: int
    title: str
    priority: int


@composite(scope="workspace_id")
@dataclass(frozen=True, slots=True)
class Dashboard:
    """One page, one declared data set. `Composite.load` runs the batched query
    set across the members and threads the single `scope=` to each."""

    projects: tuple[Project, ...]
    recent: tuple[RecentTask, ...]


@shape("SELECT id, name, status FROM projects WHERE id = :id", scope="workspace_id")
@dataclass(frozen=True, slots=True)
class ProjectDetail:
    # `WHERE id = :id` finds one project; `scope=` adds `AND workspace_id = :scope`.
    # Fetching another tenant's project by id therefore returns None — you cannot
    # reach across tenants even with a guessed id.
    id: int
    name: str
    status: str
    tasks: tuple[Task, ...] = nested(Task, on="project_id", key="id")


# ---------------------------------------------------------------------------
# App — migrations run at startup; read-only, so no mutating-route stack needed
# ---------------------------------------------------------------------------

app = App(
    config=AppConfig(template_dir=TEMPLATES_DIR),
    db=f"sqlite:///{DB_PATH}",
    migrations=str(MIGRATIONS_DIR),
)


@app.route("/")
async def dashboard(request: Request):
    """The current workspace's dashboard: projects (with tasks and each task's
    three most-recent comments) plus a recent-activity feed — one bounded set of
    queries, scoped to workspace 1."""
    page = await Composite.load(Dashboard, app.db, scope=CURRENT_WORKSPACE_ID)
    workspace = await Shape.fetch_one(Workspace, app.db, id=CURRENT_WORKSPACE_ID)
    return Page("dashboard.html", "dashboard", page=page, workspace=workspace)


@app.route("/projects/{project_id}", name="projects.detail")
async def project_detail(project_id: int, request: Request):
    """A single project, scoped. Another tenant's project id resolves to None
    (indistinguishable from 'no such project') — so we 404 either way."""
    project = await Shape.fetch_one(
        ProjectDetail, app.db, id=project_id, scope=CURRENT_WORKSPACE_ID
    )
    if project is None:
        return Template("not_found.html", project_id=project_id), 404
    return Page("project.html", "project_detail", project=project)


if __name__ == "__main__":
    app.run()

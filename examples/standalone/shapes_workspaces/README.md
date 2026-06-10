# Shapes — the verified, multi-tenant data layer

A tiny multi-tenant project tracker (**workspaces → projects → tasks →
comments**) that shows what [`chirp.data` Shapes](../../../site/content/docs/build-apps/forms-data/shapes.md)
give you that an ORM or a hand-rolled query layer does not. You are "logged in"
to workspace 1 (Acme). Workspace 2 (Globex) lives in the same tables and can
never appear in your views.

```bash
uv run python examples/standalone/shapes_workspaces/app.py
# open http://localhost:8000
```

## What it shows off

### 1. A verified SQL → render contract

Every block declares the exact `SELECT` that feeds it, co-located with a frozen
dataclass:

```python
@shape("SELECT id, name, status FROM projects WHERE id = :id", scope="workspace_id")
@dataclass(frozen=True, slots=True)
class ProjectDetail:
    id: int
    name: str
    status: str
    tasks: tuple[Task, ...] = nested(Task, on="project_id", key="id")
```

`app.check()` proves at **startup** that `project.html` reads only fields the
query actually fetched. Drop `name` from the `SELECT` but keep `{{ project.name }}`
in the template and the build fails before you serve a byte — instead of the page
silently rendering a blank where the name should be. Name a Shape that doesn't
exist in a surface contract and you get a did-you-mean:

```
ERROR shapecheck: Surface contract 'sidebar' names Shape 'ProjcetDetail',
but no such Shape is registered.  Did you mean 'ProjectDetail'?
```

### 2. Tenant isolation you cannot forget

Every Shape declares `scope="workspace_id"`. Notice there is **no hand-written
`WHERE workspace_id = ...`** anywhere — the predicate is *structurally injected*
into the parent query and every batched child query. Listing your projects is
just:

```python
projects = await Shape.fetch(Project, db, scope=current_workspace_id)
```

Fetch with `scope=1` and you get Acme's projects; `scope=2` gets Globex's; the
two never overlap. Open `/projects/3` (a Globex project) as workspace 1 and it
404s — a scoped lookup by id returns `None` for another tenant, indistinguishable
from "no such project". Omit `scope=` on a scoped Shape and it fails loud rather
than leaking. (The current workspace here is a hardcoded constant standing in for
a server-side fact like `request.user.workspace_id` — **never** a client-supplied
id.)

### 3. No N+1

The dashboard loads projects → tasks → each task's three most-recent comments
**plus** a recent-activity feed in a *bounded* number of queries — one batched
query per level, regardless of row count. The test seeds 50 extra tasks and
asserts the query count does not move:

```python
await Composite.load(Dashboard, db, scope=1)   # projects + tasks + comments + recent = 4 queries
# ...add 50 more tasks...
await Composite.load(Dashboard, db, scope=1)   # still 4 queries — not one-per-row
```

Per-task "top 3 recent comments" is compiled into a single batched window query
(`ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY created_at DESC)`), not one
query per task and not "all comments, arbitrary order".

## Files

- `app.py` — the Shapes (`Comment`, `Task`, `Project`, `RecentTask`,
  `ProjectDetail`), the `Dashboard` composite, and two read-only routes.
- `migrations/` — schema + seed (two tenants; Globex is the cross-tenant canary).
- `templates/` — `dashboard.html`, `project.html`, `not_found.html`.
- `test_app.py` — the three guarantees above, proven.

## Tests

```bash
uv run pytest examples/standalone/shapes_workspaces/
```

## Not shown

Shapes are a **read → render** contract. Writes, migrations, and dynamic queries
are out of scope — use `db.execute`, the `Query` builder, or your migration tool
for those. Shapes and an ORM can coexist: Shapes for the verified fetch-and-render
path, your write path however you like.

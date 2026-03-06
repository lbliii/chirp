# Kanban Shell

Kanban board reimplemented using the app shell pattern, chirp-ui components, and
`mount_pages` routing. Preserves all kanban features (auth, CRUD, OOB, SSE,
filtering) while showcasing chirp, kida, and chirp-ui improvements.

## Features

- **App shell** — `chirpui-app-shell` with persistent topbar, sidebar, and main content
- **mount_pages + @app.route** — Board and login via filesystem routing; API endpoints via explicit routes
- **Filter sidebar** — Priority, assignee, and tag filters with htmx partial updates
- **OOB swaps** — Add, edit, move, delete update columns and stats without full reload
- **SSE** — Simulated live activity from other users
- **Toast** — Delete notifications via chirpui toast container

## Run

```bash
pip install chirp[ui]  # or: uv add chirp[ui]
cd examples/kanban_shell && python app.py
```

Or from the chirp project root:

```bash
PYTHONPATH=examples/kanban_shell uv run python examples/kanban_shell/app.py
```

Open http://127.0.0.1:8000

## Test

```bash
pytest examples/kanban_shell/
```

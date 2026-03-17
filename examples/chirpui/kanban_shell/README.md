# Kanban Shell

Kanban board reimplemented using the app shell pattern, chirp-ui components, and
`mount_pages` routing. Preserves all kanban features (auth, CRUD, OOB, SSE,
filtering) while showcasing chirp, kida, and chirp-ui improvements.

Uses a distinct session cookie (`chirp_session_kanban_shell`) so you can run
kanban and kanban_shell on the same host/port without session collision.

## Features

- **App shell** — `chirpui-app-shell` with persistent topbar, sidebar, and main content
- **mount_pages + @app.route** — Board and login via filesystem routing; API endpoints via explicit routes
- **Filter sidebar** — Priority, assignee, and tag filters with htmx partial updates
- **OOB swaps** — Add, edit, move, delete update columns and stats without full reload
- **SSE** — Real-time board updates broadcast to all connected clients
- **Toast** — Delete notifications via chirpui toast container

## Run

```bash
pip install chirp[ui]  # or: uv add chirp[ui]
PYTHONPATH=src python examples/chirpui/kanban_shell/app.py
```

Open http://127.0.0.1:8000

## Test

```bash
pytest examples/chirpui/kanban_shell/
```

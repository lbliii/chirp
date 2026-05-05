# Reactive Tasks

Live-updating task board using Chirp's reactive system.

## What it demonstrates

- **ReactiveBus**: thread-safe pub/sub for data change events
- **DependencyIndex**: maps context paths to template blocks
- **reactive_stream()**: auto-pushes re-rendered blocks via SSE
- **ConnectionInfo**: tracks connected viewers for presence-aware streams
- **Origin filtering**: your own mutations don't echo back
- **Contract metadata**: exposes the reactive index and emitted paths to `app.check()`

Four blocks update in real time: the task list, the count badge,
the presence counter, and the last-updated timestamp.

## Run

```bash
python app.py
```

Open **two browser tabs** to `http://localhost:8000`. Add, toggle, or
delete tasks in one tab — the other tab updates within a second.

## What to observe

1. The task list in the second tab updates without a page refresh
2. The count badge updates alongside the list
3. The presence counter changes as tabs connect and disconnect
4. The timestamp shows when the last change happened
5. All updates are server-pushed via SSE — no polling

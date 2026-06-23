# Reactive Tasks

Live-updating task board using Chirp's reactive system.

## What it demonstrates

- **ReactiveBus**: thread-safe pub/sub for data change events
- **DependencyIndex**: maps context paths to template blocks
- **reactive_stream()**: auto-pushes re-rendered blocks via SSE
- **ConnectionInfo**: tracks connected viewers for presence-aware streams
- **Audience-ready streams**: the same connection metadata supports
  `ChangeEvent(audience=...)` when updates should go only to selected users
- **Origin filtering**: your own mutations don't echo back (pass `origin=` on the stream when emitting with `ChangeEvent(origin=...)`)
- **Changed-path context builders**: `reactive_stream()` passes
  `changed_paths` into a one-argument `context_builder` for selective data loading
- **on_disconnect**: presence count updates when tabs close
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
6. Mutations in the originating tab do not echo back over SSE (origin filtering)

## SSE wiring

Each live region uses a **named channel** matching its block name:

- `sse-swap="task_list"`, `sse-swap="task_count"`, etc.
- `reactive_stream()` yields `Fragment(..., target=block_name)` for each affected block.

The `sse-connect` wrapper is on `<main>` with `hx-disinherit="hx-target hx-swap"`.
Individual sinks carry their own `hx-target` / `hx-swap`.

## Contract checks

This example registers reactive metadata so `app.check()` can validate the stream:

| Key | Value in this app |
|-----|-------------------|
| `reactive_index` | the `DependencyIndex` used by the stream |
| `reactive_emitted_paths` | `{"tasks", "presence"}` |
| `reactive_connection_scopes` | `{"board"}` |

If an example starts emitting audience-filtered events, add matching entries to
`reactive_audience_scopes` as well.

From the repository root:

```bash
uv run pytest examples/standalone/reactive_tasks -q
```

The test suite asserts page rendering, mutation fragments, SSE response
headers, named fragment events over the wire (`task_list`, `task_count`), and
clean `check_hypermedia_surface()` output for the reactive metadata and template
wiring.

## Browser smoke

1. Open two tabs to `/`.
2. Confirm the presence counter reads `2 viewing` (or higher if more tabs are open).
3. Add a task in tab A — tab B's list, count badge, and timestamp update without refresh.
4. Close tab A — tab B's presence counter decrements within a second.

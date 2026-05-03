---
title: Kanban Shell
description: App-shell Kanban board with OOB swaps, SSE, auth, and filters
draft: false
weight: 70
lang: en
type: doc
tags: [examples, chirp-ui, app-shell, sse, oob]
keywords: [kanban, app shell, sse, oob, chirp-ui]
category: examples
---

## What It Teaches

This is the larger app-shell example. Use it when you need to understand how
multiple Chirp surfaces interact in one app: auth, mounted pages, filters,
drag-and-drop style mutations, OOB swaps, SSE broadcasts, and toast updates.

It demonstrates:

- persistent `chirpui-app-shell` chrome
- filesystem pages plus explicit API routes
- filter sidebar updates with htmx
- OOB swaps for columns and stats
- SSE live sync across connected clients
- a distinct session cookie so paired examples do not collide

## Run It

```bash
PYTHONPATH=src python examples/chirpui/kanban_shell/app.py
```

Open `http://127.0.0.1:8000/`.

## Test It

```bash
pytest examples/chirpui/kanban_shell/
```

## Contract Surface

This example is the broadest executable-doc surface for app-shell behavior. It
is the right fixture when changing OOB regions, SSE integration, shell actions,
auth middleware setup, or route/page conventions.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/kanban_shell/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/kanban_shell/README.md)

## Next

- [[docs/guides/app-shell|App Shells]]
- [[docs/guides/oob-registry|OOB Registry]]
- [[docs/streaming/server-sent-events|Server-Sent Events]]

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

A full Kanban board built the way a real Chirp app is built: a persistent
[[docs/build-apps/ui-extensions/app-shell|app shell]], drag-style mutations that
swap only the columns and stats that changed, and a live feed so every connected
client sees the same board. Reach for this example when you want to see how the
pieces fit together in one app — auth,
[[docs/build-apps/pages-navigation/filesystem-routing|filesystem pages]]
alongside explicit API routes, htmx
[[docs/build-apps/html-fragments/fragments|fragments]],
[[docs/quality/contracts-debugging/oob-registry|out-of-band swaps]], and
[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] —
rather than one feature in isolation. If you only need one technique, start from
the [[docs/examples/contacts-shell|smaller examples]]; this is the "everything
together" reference.

It demonstrates:

- persistent `chirpui-app-shell` chrome
- filesystem pages plus explicit API routes
- filter sidebar updates with htmx
- OOB swaps for columns and stats
- SSE live sync across connected clients

:::{note}
This example sets a distinct session cookie (`chirp_session_kanban_shell`) so
you can run it alongside the plain Kanban example on the same host and port
without the two sharing — or clobbering — each other's session.
:::

## Run It

::::{code-tabs}

```bash title="Run"
PYTHONPATH=src python examples/chirpui/kanban_shell/app.py
```

```bash title="Test"
pytest examples/chirpui/kanban_shell/
```

::::

Then open `http://127.0.0.1:8000/`.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/kanban_shell/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/kanban_shell/README.md)

:::{dropdown} For contributors: the canonical app-shell fixture
:icon: users

This example is the broadest end-to-end exercise of app-shell behavior in the
repo. It is the fixture to reach for when changing OOB regions, SSE integration,
shell actions, auth middleware setup, or route and page conventions — a change
that breaks the shell contract tends to break here first.
:::{/dropdown}

## Next

- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/quality/contracts-debugging/oob-registry|OOB Registry]]
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]

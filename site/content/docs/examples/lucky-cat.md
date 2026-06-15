---
title: Lucky Cat
description: Flagship ChirpUI crypto-exchange demo on server-owned signals
draft: false
weight: 15
lang: en
type: doc
tags: [examples, chirp-ui, app-shell, signals, sse, suspense, oob]
keywords: [lucky cat, crypto exchange, signals, app shell, suspense, oob, sse, chirp-ui]
category: examples
---

## What It Teaches

Lucky Cat is the marquee ChirpUI example: a Maneki-neko **$MEOW** crypto
exchange built entirely on the app-shell lane. Use it to see how a real,
multi-page product wires return types, signals, and the secure-by-default stack
together — there is no client-side framework, only htmx and server-owned state.

**Live demo:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app)

**Location:** `examples/chirpui/lucky_cat/`

It demonstrates:

- a full-viewport `chirpui-app-shell` with a brand topbar, a cross-page ticker
  strip, and a two-tier (icon + route-context) collapsible rail
- a **markets grid** landing and a **market-detail** page (`/markets/{symbol}`)
  with an interactive price chart, a depth-bar order book, and a recent-trades
  tape, each fed by a per-market `EventStream`
- a place/cancel-order **trade flow**: a clean fill returns one `FormAction`
  whose multi-target OOB set swaps positions, balance, the open-order badge, and
  a toast; an invalid order returns `ValidationError` for a **422** re-render
  with field errors and submitted values preserved
- a `Suspense` **portfolio dashboard** whose six panels paint as skeletons and
  stream in as their awaitables resolve (`{% if x is deferred %}`, `defer_blocks`,
  `defer_map`)
- a starred-markets **watchlist**, an **activity feed**, and a Cmd/Ctrl-K
  **command palette**
- the cross-page **ticker**, **$MEOW balance**, and **notification bell** all
  bound to server-owned `signal()`s over one `/_chirp/live` SSE connection
  (declare-once / bind-many, with pure `derived` signals for the bell's
  unread-count pill)

## Run It

```bash
pip install bengal-chirp[ui]
PYTHONPATH=src python examples/chirpui/lucky_cat/app.py
```

Open `http://127.0.0.1:8000/`. `/health` returns `200 ok` (the Railway
healthcheck).

## Test It

```bash
pytest examples/chirpui/lucky_cat/
```

## Deploy It

The example ships a `Dockerfile` and `railway.toml` so it can run as a
standalone Railway service: `python app.py` binds `0.0.0.0:$PORT` through
`AppConfig.from_env()`, and the healthcheck targets `/health`. Keep it a single
web replica — the demo holds all state (wallet, trade store, SimFeed, signal
bus) in process memory. See [[docs/quality/deployment/production|Production
Deployment]] for the full shape.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/README.md)

## Next

- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]]
- [[docs/examples/suspense-dashboard|Suspense Dashboard]]
- [[docs/examples/kanban-shell|Kanban Shell]]

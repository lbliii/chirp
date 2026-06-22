---
title: Realtime decision tree
description: Pick Stream, Suspense, EventStream, signal(), or OOB for live and streaming UI
draft: false
weight: 15
lang: en
type: doc
tags: [streaming, suspense, sse, signals, oob, realtime]
keywords: [stream, suspense, eventstream, signal, oob, decision, lucky cat]
category: guide
icon: git-branch
---

## One question at a time

Chirp has five mechanisms that move HTML after (or while) a page loads. Pick by
**when** the update happens and **how many targets** it must hit in one round
trip — not by habit.

:::{list-table} Decision tree
:header-rows: 1

* - Situation
  - Reach for
  - Transport
* - Initial render, slow sections, **one HTTP trip**, shell paints first
  - `Suspense`
  - Single chunked response + OOB swaps
* - Initial render, SEO-heavy sections, **no shell-first step**
  - `Stream`
  - Single chunked response
* - Post-load live region on **one page** (chart, book, tape)
  - `EventStream` + `sse_scope()`
  - Long-lived SSE on that page
* - Cross-page chrome, fan-out, or post-mutation push to many bindings
  - `signal()` on `/_chirp/live`
  - One shared SSE connection
* - Multi-target mutation response in the **same round trip**
  - `OOB` / `FormAction` fragments
  - Normal htmx POST response
:::

**Rule of thumb:** initial render that streams → `Suspense` (or `Stream` when you
want progressive first byte without a skeleton shell). Updates after the page is
live → `EventStream` for page-local regions, `signal()` when the same value must
update chrome on every page. Several DOM targets from one POST → `OOB`.

See also [[docs/about/core-concepts/return-values|Return values]] for the full
type reference and [[docs/build-apps/streaming-updates/html-streaming|Streaming
HTML & Suspense]] for template patterns.

## Lucky Cat map

The flagship [[docs/examples/lucky-cat|Lucky Cat]] example uses all five on purpose
— use it as a worked map, not as the default for a first app.

| Feature | Route / trigger | Mechanism | Why this one |
|---------|-----------------|-----------|--------------|
| Portfolio dashboard | `GET /portfolio` | `Suspense` | Shell + six deferred panels, one trip |
| Market detail live blocks | `GET /markets/{symbol}/stream` | `EventStream` | Page-local chart/book/tape after load |
| Free-threading proof panel | `GET /ft/stream` | `EventStream` | Same — one page, one live region |
| Topbar ticker, balance, bell | `/_chirp/live` | `signal()` | Cross-page chrome; one connection |
| Markets lobby board | `/_chirp/live` (derived cascade) | `signal()` | One snapshot → three regions in lockstep |
| Deposit / trade fill | `POST /deposit`, `POST /trade/order` | `signal()` emit + 204 | Balance/bell update without response body |
| Watchlist star toggle | `POST /watchlist/toggle` | `OOB` | Star + rail count (+ optional card delete) |
| Trade fill (positions table) | `POST /trade/order` | `FormAction` + OOB fragments | Form reset + table + toast same POST |
| Trending / Research grids | `GET` with htmx | `Page` / `Fragment` | Snapshot per swap — no live re-rank |

Doctrine and footguns for the shell live in the example's `DESIGN.md` §4 and §7.

## Start simpler

Before combining all five in one app, learn each mechanism in isolation:

1. [[docs/examples/suspense-dashboard|Suspense dashboard]] — one deferred panel
2. [[docs/examples/sse|SSE]] — minimal post-load stream
3. [[docs/examples/contacts-shell|Contacts shell]] — boosted nav + `_actions.py`
4. [[docs/examples/lucky-cat|Lucky Cat]] — capstone that composes everything

:::{related}
- [[docs/build-apps/streaming-updates/_index|Streaming and updates]]
- [[docs/build-apps/streaming-updates/signals|Signals]]
- [[docs/build-apps/html-fragments/fragments|Fragments and OOB]]
:::

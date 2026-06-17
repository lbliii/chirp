---
title: Shells
description: The three root layouts you can extend, when to pick each, and what is not a shell
draft: false
weight: 33
lang: en
type: doc
tags: [shells, layout, boost, htmx, app-shell]
keywords: [shell, app-shell, boost.html, shell.html, app_shell_layout, root layout]
category: guide
---

## What a shell is

A **shell** is the root layout your page templates extend. It owns the
document root (`<html>`, `<head>`, `<body>`), loads htmx, and declares the
**htmx-boost contract** — the target id, swap mode, and `hx-select` filter
that govern how [[docs/build-apps/ui-extensions/boosted-navigation|boosted navigation]]
flows into the page.

Pick exactly one shell per app. Your page templates,
[[docs/build-apps/html-fragments/fragments|fragments]], and feature modules
render *inside* the shell's outlet.

## The three shells

Chirp ships two; chirp-ui adds one more.

:::{list-table}
:header-rows: 1

* - Shell
  - Comes from
  - When to pick it
* - `chirp/layouts/boost.html`
  - core
  - htmx-boost SPA-style nav, no opinionated chrome
* - `chirp/layouts/shell.html`
  - core
  - Fragment-only apps (LLM/RAG playgrounds, dashboards, form-heavy UIs) — no `hx-select`, fragments flow exactly where `hx-target` says
* - `chirpui/app_shell_layout.html`
  - chirp-ui
  - Sidebar/topbar app chrome with breadcrumbs, shell actions, and OOB regions pre-wired
:::

The decisive question is whether your app needs **persistent chrome** —
sidebar, topbar, breadcrumbs that survive boosted navigation:

- **Yes** → `app_shell_layout.html`. See [[docs/build-apps/ui-extensions/app-shell|App Shells]].
- **No, but you want SPA-style nav** → `boost.html`. See [[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]].
- **No, fragment swaps only** → `shell.html`.

## The `hx-select` distinction

The biggest hidden difference between the three is what the outlet element
(`#main`) sets for `hx-select`:

- **`boost.html`** — `hx-select="#page-content"`. Filters every response.
  Correct for boosted nav; **silently discards** fragment responses that
  don't contain `#page-content`.
- **`shell.html`** — no `hx-select`. Forms and fragment swaps land exactly
  where `hx-target` says, with no filtering.
- **`app_shell_layout.html`** — `hx-select="#page-content"` on its `<main>`
  outlet. Same boost contract as `boost.html`, plus persistent chrome.

:::{warning} A fragment-heavy app on `boost.html` updates nothing
If you build a fragment-heavy app on `boost.html`, form posts return `200 OK`
but the UI never changes — the `hx-select="#page-content"` filter discards any
response that doesn't contain that id. The htmx debug overlay shows
"Empty hx-select" on the triggering element.

The fix is a one-line change: extend `shell.html` instead (no global
`hx-select`), and remove any defensive `hx-disinherit="hx-select"` shims that
were working around the inherited selector.
:::

`chirp check` flags this mismatch via the `select_inheritance` rule (a
WARNING) when a mutating element may silently discard its response. See
[[docs/quality/contracts-debugging/categories|the select_inheritance contract rule]].

## What is *not* a shell

Feature modules like `chirp.docs` ship templates with their own visual chrome
(sidebar nav, search box, content area). They look shell-like, but they are
**not shells** — they render *inside* the outlet of whatever shell you extend.
A feature module's page templates do not establish `<html>`/`<head>`/`<body>`,
do not load htmx, and do not declare the boost contract. They render as the
content of a route handler (typically `Page("chirp_docs/doc_page.html",
"doc_content", doc=doc)`) and compose into the shell's `{% block content %}`
slot.

Mount `chirp.docs` in an app that extends `app_shell_layout.html` and the docs
sidebar lives *inside* the chirp-ui main outlet — not as a peer of the chirp-ui
sidebar. The shell stays in charge of the page frame.

:::{dropdown} Advanced: roll your own shell
Most apps extend one of the three shells above. If you need a custom root
layout, replicate the boost contract on the outlet element:

```html
<main id="main" tabindex="-1"
      hx-boost="true" hx-target="#main" hx-swap="innerHTML" hx-select="#page-content">
  <div id="page-content">
    {% block content %}{% end %}
  </div>
</main>
```

Sidebar links *outside* `#main` need their own `hx-target="#main"` and
`hx-select="#page-content"` since they don't inherit from the `#main` element.
See `examples/chirpui/kanban_shell` for a worked example.
:::{/dropdown}

:::{note} See also
- [[docs/build-apps/ui-extensions/app-shell|App Shells]] — building with chirp-ui's `app_shell_layout.html`
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]] — the boost contract, cross-shell redirects, debug warnings
- [[docs/build-apps/ui-extensions/ui-layers|UI layers & shell regions]] — vocabulary for app shell vs page chrome vs surface chrome
- [[docs/build-apps/html-fragments/layout-patterns|Layout Patterns]] — block, include, call constructs inside any shell
:::

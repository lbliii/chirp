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

A **shell** is the root layout your templates extend. It owns the document
root (`<html>`, `<head>`, `<body>`), loads htmx, and declares the
**htmx-boost contract** — the target id, swap mode, and `hx-select` filter
that govern how boosted navigation flows into the page.

**Pick exactly one shell per app.** Page templates, fragments, and feature
modules render *inside* the shell's outlet.

## The three shells

Chirp ships two; chirp-ui adds one more.

| Shell | Comes from | When to pick it |
|---|---|---|
| `chirp/layouts/boost.html` | core | htmx-boost SPA-style nav, no opinionated chrome |
| `chirp/layouts/shell.html` | core | Fragment-only apps (LLM/RAG playgrounds, dashboards, form-heavy UIs) — no `hx-select`, fragments flow exactly where `hx-target` says |
| `chirpui/app_shell_layout.html` | chirp-ui | Sidebar/topbar app chrome with breadcrumbs, shell actions, and OOB regions pre-wired |

The decisive question is whether your app needs **persistent chrome** —
sidebar, topbar, breadcrumbs that survive boosted navigation:

- **Yes** → `app_shell_layout.html`. See [App Shells](/chirp/docs/build-apps/ui-extensions/app-shell/).
- **No, but you want SPA-style nav** → `boost.html`. See [Boosted Navigation](/chirp/docs/build-apps/ui-extensions/boosted-navigation/).
- **No, fragment swaps only** → `shell.html`.

## The `hx-select` distinction

The biggest hidden difference between the three is what `<main>` sets for
`hx-select`:

- **`boost.html`** — `hx-select="#page-content"`. Filters every response.
  Correct for boosted nav; **silently discards** fragment responses that
  don't contain `#page-content`.
- **`shell.html`** — no `hx-select`. Forms and fragment swaps land exactly
  where `hx-target` says, with no filtering.
- **`app_shell_layout.html`** — `hx-select="#page-content"` on `<main>` plus
  per-link `hx-boost` on sidebar links. Same boost contract as `boost.html`,
  plus persistent chrome.

If you build a fragment-heavy app on `boost.html`, form posts return 200 OK
but the UI never updates. The HTMX debug overlay will show "Empty hx-select"
on the triggering element. The fix is a one-line change to extend `shell.html`
instead — and remove any defensive `hx-disinherit="hx-select"` shims that
were working around the inherited selector.

`chirp check` catches the mismatch via the `select_inheritance` rule when a
mutating element may silently discard its response.

## What is *not* a shell

A common point of confusion: feature modules like **`chirp.docs`** ship
templates with their own visual chrome (sidebar nav, search box, content
area). They look shell-like, but they are **not shells.**

```
chirp.docs / future forum / your custom feature module
   └── ships page templates (doc_page.html, doc_list.html, …)
       └── render INSIDE the outlet of whatever shell you extend
```

Page templates from a feature module:

- Do **not** establish `<html>`, `<head>`, `<body>`, or load htmx.
- Do **not** declare the boost contract (target, swap, select).
- Render as the **content** of a route handler — typically via
  `Page("chirp_docs/doc_page.html", "doc_content", doc=doc)`.
- Compose into the shell's `{% block content %}` slot (or get returned as a
  fragment).

If you mount `chirp.docs` in an app that extends `app_shell_layout.html`, the
docs sidebar lives *inside* the chirp-ui main outlet — not as a peer of the
chirp-ui sidebar. The shell stays in charge of the page frame.

## Custom shells

To roll your own shell instead of extending one of the three, replicate the
boost contract on `<main>`:

```html
<main id="main" tabindex="-1"
      hx-boost="true" hx-target="#main" hx-swap="innerHTML" hx-select="#page-content">
  <div id="page-content">
    {% block content %}{% end %}
  </div>
</main>
```

Sidebar links *outside* `#main` need their own `hx-target="#main"` and
`hx-select="#page-content"` since they don't inherit from the `<main>`
element. See `examples/chirpui/kanban_shell` for a worked example.

## Related

- [App Shells](/chirp/docs/build-apps/ui-extensions/app-shell/) — building with chirp-ui's `app_shell_layout.html`
- [Boosted Navigation](/chirp/docs/build-apps/ui-extensions/boosted-navigation/) — the boost contract, cross-shell redirects, debug warnings
- [UI layers & shell regions](/chirp/docs/build-apps/ui-extensions/ui-layers/) — vocabulary for app shell vs page chrome vs surface chrome
- [Layout Patterns](/chirp/docs/build-apps/html-fragments/layout-patterns/) — block, include, call constructs inside any shell

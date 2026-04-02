---
title: UI layers & shell regions
description: Vocabulary for app shell, page chrome, surface chrome, and stable OOB targets
draft: false
weight: 34
lang: en
type: doc
tags: [app-shell, htmx, layout, glossary]
keywords: [shell, chrome, page-content, OOB, fragment targets]
category: guide
---

## Why this page exists

Chirp + chirp-ui use several overlapping words (**shell**, **chrome**, **fragments**). This guide fixes one vocabulary for docs, APIs, and templates.

## The four layers

| Layer | Official term | Where it lives | Updates when |
|-------|---------------|----------------|--------------|
| **L1** | **App shell** | Topbar, sidebar, wrapper ``#main`` — outside ``#page-content`` | Boosted navigation + OOB for shell regions |
| **L2** | **Page chrome** | Inside ``#page-content`` (headers, tabs, route toolbars) | Broader fragment targets (e.g. ``#page-root``) |
| **L3** | **Shell actions** | ``#chirp-shell-actions`` (subtype of L1) | Route ``ShellActions`` + OOB |
| **L4** | **Surface chrome** | Borders/padding/scroll around **components** (cards, panels, bento cells) | Local swaps only — *not* the app shell |

**Rule:** In prose and APIs, **shell** means **L1** (persistent frame). Do not call card borders “shell”; use **surface chrome**.

## Boosted navigation and ``hx-select``

``#main`` participates in boosted navigation; the fragment selector depends on the layout:

| Layout | ``hx-select`` on ``#main`` | Required in page HTML |
|--------|---------------------------|------------------------|
| ``chirpui/app_shell_layout.html`` / ``app_shell`` | ``#page-root`` | ``<div id="page-root">…</div>`` inside the content block |
| ``chirp/layouts/boost.html`` | ``#page-content`` | The layout’s ``#page-content`` wrapper |

A block named ``page_root`` does **not** create ``id="page-root"``; omitting that element yields an empty main area after sidebar links.

## Shell regions (stable DOM ids)

Shell **regions** are elements with fixed ``id`` attributes that htmx updates with **out-of-band** swaps after the primary ``#main`` swap. Import canonical ids from :mod:`chirp.shell_regions`:

| Constant | Default element id | Role |
|----------|-------------------|------|
| ``DOCUMENT_TITLE_ELEMENT_ID`` | ``chirpui-document-title`` | Document title (``<title>``) |
| ``SHELL_ACTIONS_TARGET`` | ``chirp-shell-actions`` | Route-scoped topbar actions |

``SHELL_ELEMENT_IDS`` is a frozenset of documented ids for tooling and tests.

Apps may add more OOB targets (breadcrumbs, sidebars); register them in the layout contract and document them locally.

## Fragment targets vs shell

Registered **fragment targets** (``FragmentTargetRegistry``) map ``HX-Target`` to Kida blocks. ``triggers_shell_update`` means: “this swap may change shell regions; run shell negotiation (including ``shell_actions`` OOB).” Set it ``False`` for narrow in-page swaps (e.g. ``#page-content-inner``) that should not refresh the topbar.

## HTMX ordering note

htmx applies the **primary** swap before **out-of-band** fragments. chirp-ui’s ``app_shell_layout.html`` includes a small ``htmx:beforeSwap`` handler that clears ``#chirp-shell-actions`` when the response contains a matching OOB, avoiding one frame of stale actions. See chirp-ui app shell docs for details.

## See also

- [App shells](./app-shell.md) — navigation model and ``use_chirp_ui``
- [chirp-ui App Shell](https://lbliii.github.io/chirp-ui/docs/app-shell/) — layouts and components

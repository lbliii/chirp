---
title: Contacts Shell
description: Contacts CRUD rebuilt with chirp-ui app shell and mounted pages
draft: false
weight: 60
lang: en
type: doc
tags: [examples, chirp-ui, app-shell, pages]
keywords: [contacts shell, chirp-ui, app shell, mount pages]
category: examples
---

## What It Teaches

This example is the app-shell version of the plain contacts app. Use it when
you are moving from isolated htmx fragments to a persistent shell with mounted
pages and shell-aware swaps.

It demonstrates:

- `use_chirp_ui(app)` and `app.mount_pages()`
- `chirpui/app_shell_layout.html`
- route-scoped shell actions
- query-backed search state
- inline row editing without stale filtered results
- typed repeated-field parsing with `form_from()`

## Run It

```bash
PYTHONPATH=src python examples/chirpui/contacts_shell/app.py
```

## Test It

```bash
pytest examples/chirpui/contacts_shell/
```

## Contract Surface

The example is useful for app-shell contract work: route metadata, mounted
pages, shell actions, boosted navigation, and fragment scopes all need to agree.
Use it when changing pages, shells, route contracts, or ChirpUI-facing docs.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/README.md)

## Next

- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/build-apps/pages-navigation/route-directory|Route Directory]]
- [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]]

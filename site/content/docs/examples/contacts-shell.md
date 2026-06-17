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

This is the same contacts CRUD app as [[docs/examples/contacts|Contacts]], rebuilt
on the [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] app shell — a persistent
page chrome (sidebar, topbar) that stays put while htmx swaps the content region.
Reach for this version once you have outgrown isolated fragments and want
[[docs/build-apps/pages-navigation/filesystem-routing|filesystem-mounted pages]],
URL-backed search state, and shell-aware navigation.

It demonstrates:

- `use_chirp_ui(app)` and `app.mount_pages()`
- `chirpui/app_shell_layout.html` for the persistent shell
- route-scoped [[docs/build-apps/ui-extensions/app-shell|shell actions]] from `_context.py`
- query-backed search state
- inline row editing without stale filtered results
- typed repeated-field parsing with [[docs/build-apps/forms-data/forms-validation|`form_from()`]]

## When to Reach for It

Both contacts examples cover the same CRUD domain. Pick by the UI layer you need.

:::{list-table}
:header-rows: 1

* - Example
  - UI layer
  - Use it for
* - [[docs/examples/contacts|Contacts]]
  - Plain htmx, no shell
  - The fragment / OOB / validation baseline in a single template
* - **Contacts Shell**
  - chirp-ui app shell + mounted pages
  - Persistent chrome, filesystem pages, URL-backed search state
:::

## Minimal Example

The whole app is about 50 lines: `use_chirp_ui` installs the shell,
`mount_pages` wires the filesystem routes, and one explicit route parses a
repeated `contact_ids` field with `form_from`.

```python
import sys
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, form_from, use_chirp_ui
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

ROOT_DIR = Path(__file__).parent
PAGES_DIR = ROOT_DIR / "pages"

sys.path.insert(0, str(ROOT_DIR))

from chirp_ui import register_colors
from contacts_shell_store import GROUP_COLORS, reset_store, store


@dataclass(frozen=True, slots=True)
class ContactSelectionForm:
    contact_ids: list[int]


config = AppConfig(template_dir=PAGES_DIR, debug=True)
app = App(config=config)

use_chirp_ui(app)
register_colors(GROUP_COLORS)
app.add_middleware(SessionMiddleware(SessionConfig(secret_key="contacts-shell-dev-secret")))
app.add_middleware(CSRFMiddleware())
reset_store()
app.mount_pages(str(PAGES_DIR))


@app.route("/contacts/selection", methods=["POST"])
async def select_contacts(request: Request):
    form = await form_from(request, ContactSelectionForm)
    selected = [contact for contact_id in form.contact_ids if (contact := store.get(contact_id))]
    return Fragment("contacts/selection.html", "selection_preview", selected_contacts=selected)


if __name__ == "__main__":
    app.run()
```

*Source: [`examples/chirpui/contacts_shell/app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/app.py).*

The `contact_ids: list[int]` annotation is the point of the selection route:
`form_from` parses repeated `contact_ids` form fields into a typed list of ints.

## Run It

```bash
PYTHONPATH=src python examples/chirpui/contacts_shell/app.py
```

Open `http://127.0.0.1:8000/`.

:::{tip}
This example sets its own session secret, so it uses a distinct session cookie.
You can run it alongside the plain [[docs/examples/contacts|Contacts]] app without
the two sessions colliding.
:::

## Test It

```bash
pytest examples/chirpui/contacts_shell/
```

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/README.md)

:::{dropdown} When this example is a useful contract fixture
This app exercises app-shell behavior end to end: route metadata, mounted pages,
shell actions, boosted navigation, and fragment scopes all have to agree. It is a
good fixture when you change pages, shells, route contracts, or chirp-ui-facing
docs.
:::{/dropdown}

## Next

- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/build-apps/pages-navigation/route-directory|Route Directory]]
- [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]]

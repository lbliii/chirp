# Contacts Shell

A `chirp-ui` version of the contacts example built with mounted pages and a
persistent app shell.

It demonstrates:

- `use_chirp_ui(app)` with `app.mount_pages()`
- `chirpui/app_shell_layout.html`
- route-scoped `ShellActions`
- query-backed search state
- inline row editing without stale filtered results

## Run

```bash
PYTHONPATH=src python examples/chirpui/contacts_shell/app.py
```

## Test

```bash
pytest examples/chirpui/contacts_shell/
```

## Why This Exists

`contacts/` stays the plain htmx CRUD baseline.

`contacts_shell/` shows the same domain in the current Chirp + `chirp-ui`
app-shell style, where search state lives in the URL and mutations re-render the
current filtered view from the server.

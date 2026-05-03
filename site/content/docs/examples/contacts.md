---
title: Contacts
description: Plain htmx CRUD with validation, OOB swaps, and response headers
draft: false
weight: 30
lang: en
type: doc
tags: [examples, htmx, forms, fragments, oob]
keywords: [contacts, crud, validation, oob, htmx]
category: examples
---

## What It Teaches

This is the baseline Chirp CRUD app without ChirpUI. Read it after the first
fragment app when you want realistic htmx workflows:

- `Page(...)` for full page vs fragment negotiation
- `Fragment(...)` for search and delete updates
- `ValidationError(...)` for 422 form re-renders
- `OOB(...)` for updating the table and count in one response
- HX response headers for toast-style UX
- frozen dataclasses plus a lock for thread-safe in-memory state

## Run It

```bash
PYTHONPATH=src python examples/standalone/contacts/app.py
```

Open `http://127.0.0.1:8000/`.

## Test It

```bash
pytest examples/standalone/contacts/
```

## Contract Surface

This example is a good fixture for htmx correctness: table rows, form fragments,
OOB counters, and validation errors all depend on named blocks matching the
Python return values. It also shows why broad `hx-target` selectors are risky:
the table target is an explicit `#contact-table`, and OOB updates use the
separate `#contact-count` target.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/app.py)
- [`contacts.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/templates/contacts.html)
- [`test_app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/test_app.py)

## Next

- [[docs/data/forms-validation|Forms and Validation]]
- [[docs/guides/oob-registry|OOB Registry]]
- [[docs/tutorials/htmx-patterns|htmx Patterns]]

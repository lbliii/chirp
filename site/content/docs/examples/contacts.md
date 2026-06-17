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

A no-dependency htmx CRUD app — add, search, edit, and delete contacts — built on
plain Chirp return types and in-memory state. Reach for it after
[[docs/get-started/first-fragment-app|your first fragment app]] when you want a
realistic mutation loop: a search box that swaps a table, a form that re-renders
with 422 validation errors, an add that updates the table and its count badge in
one response, and a delete that re-renders the table and fires an `HX-Trigger`
event to drive a toast.

## What It Teaches

- [[docs/about/core-concepts/return-values|`Page`]] for full-page vs. fragment negotiation
- [[docs/build-apps/html-fragments/fragments|`Fragment`]] for search and delete updates
- [[docs/build-apps/forms-data/forms-validation|`ValidationError`]] for 422 form re-renders
- [[docs/quality/contracts-debugging/oob-registry|`OOB`]] for updating the table and count in one response
- an `HX-Trigger` event that drives a toast after delete
- frozen dataclasses plus a lock for thread-safe in-memory state

## Run It

::::{code-tabs}

```bash title="Run"
PYTHONPATH=src python examples/standalone/contacts/app.py
```

```bash title="Test"
pytest examples/standalone/contacts/
```

::::

Then open `http://127.0.0.1:8000/`.

## One Response, Two Targets

Adding a contact updates two regions in a single response: the table re-renders,
and the heading's count badge swaps out of band. The handler returns one `OOB`
wrapping two `Fragment`s.

```python
@app.route("/contacts", methods=["POST"], name="contacts.add")
async def add_contact(request: Request):
    form = await request.form()
    result = validate(form, _CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts.html", "contact_form",
            retarget="#form-section",
            errors=result.errors,
            form={"name": form.get("name", ""), "email": form.get("email", "")},
        )

    _add_contact(form.get("name", ""), form.get("email", ""))
    contacts = _get_contacts()
    return OOB(
        Fragment("contacts.html", "contact_table", contacts=contacts),
        Fragment("contacts.html", "contact_count", target="contact-count", count=len(contacts)),
    )
```

*Source: [`examples/standalone/contacts/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/app.py).*

:::{tip} Scope swaps to explicit IDs
Each fragment targets one named block and one DOM id — the table swaps into
`#contact-table`, the count into `#contact-count`. Avoid broad `hx-target`
selectors: when a region is updated out of band, point it at the exact id it
owns so an `OOB` swap can never clobber an unrelated part of the page.
:::

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/app.py)
- [`contacts.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/templates/contacts.html)
- [`test_app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/contacts/test_app.py)

## Next

- [[docs/build-apps/forms-data/forms-validation|Forms and Validation]]
- [[docs/quality/contracts-debugging/oob-registry|OOB Registry]]
- [[docs/tutorials/htmx-patterns|htmx Patterns]]

:::{related}
:::

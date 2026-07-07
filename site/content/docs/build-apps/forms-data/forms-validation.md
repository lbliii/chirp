---
title: Forms & Validation
description: Parse POST bodies into typed dataclasses, validate them in one pass, and re-render the form with errors.
draft: false
weight: 20
lang: en
type: doc
tags: [forms, validation, multipart]
keywords: [forms, validation, multipart, file-upload, validation-result, rules, form-from, form-or-errors, form-values, form-macros, dataclass-binding]
category: guide
---

## Overview

Chirp parses a POST body into form data, binds it to a frozen dataclass with type
coercion, and validates it in one pass. You declare a dataclass, attach validation
rules to its fields with `Annotated`, and call `form_or_errors()`. On bad input it
returns a `ValidationError` — a 422 [fragment](/chirp/docs/build-apps/html-fragments/fragments/)
that re-renders your form with per-field messages. On good input it returns your
typed instance.

If you come from Flask or Django, this replaces the `request.form` dict-juggling
and the `Form`/`ModelForm` class with one declarative schema.

:::{note} Which entry point?
Use **`form_or_errors()`** for the common case: a form bound to a dataclass.
Drop to manual `request.form()` + [`validate()`](#manual-validation-without-a-dataclass)
only when you are *not* binding to a dataclass — for example validating raw query
params or a partial sub-form.
:::

## The happy path: declare, bind, validate

Declare a [frozen dataclass](/chirp/docs/build-apps/forms-data/shapes/) with
`frozen=True, slots=True`, attach rules with `Annotated`, and let `form_or_errors()`
do binding and validation in the same call.

:::{since} 0.8
`form_or_errors()` runs `chirp.validation` rules attached via `Annotated` in the
same pass as binding — no separate `validate()` call, no form class.
:::

```python
from dataclasses import dataclass
from typing import Annotated

from chirp import App, Request, form_or_errors, FormAction, ValidationError
from chirp.validation import required, max_length

app = App()


@dataclass(frozen=True, slots=True)
class TaskForm:
    title: Annotated[str, required, max_length(100)]
    description: str = ""


@app.route("/tasks", methods=["POST"])
async def add_task(request: Request):
    result = await form_or_errors(request, TaskForm, "tasks.html", "task_form")
    if isinstance(result, ValidationError):
        return result  # 422 fragment with per-field errors + raw values

    # result is a TaskForm — title is bound and validated.
    save_task(result.title, result.description)
    return FormAction("/tasks")
```

A rule in the `Annotated` metadata is any callable matching `(str) -> str | None`.
Non-callable metadata is ignored, so the same annotation can carry doc strings or
sentinels for other tooling. A plain dataclass with no `Annotated` rules runs only
binding — behavior is unchanged.

Rule errors and binding (type-coercion) errors **merge per field**: a bad `int`
on one field and a failed rule on another both land in `result.context["errors"]`,
and the raw submitted values come back in `result.context["form"]` for
re-population. Falsy-but-valid values stay valid — `"0"` satisfies `required`, and
an omitted `list[str]` binds to `[]` without being flagged.

### Coerced field types

`form_or_errors()` (via `form_from()`) coerces each field to its declared type.
Fields without a default are required; a missing required field yields an error.

| Annotation | Coerced from a form string to |
|---|---|
| `str` | stripped string |
| `int` / `float` | number (`ValueError` → field error) |
| `bool` | `True` for `"true"`/`"1"`/`"yes"`/`"on"` |
| `datetime.date` / `datetime.datetime` | ISO 8601 |
| `decimal.Decimal` / `uuid.UUID` | parsed value |
| `enum.Enum` subclass | member by value, then by name |
| `list[T]` | repeated fields (checkbox groups, multi-selects); missing → `[]` |

### Extra template context and retargeting

`form_or_errors()` passes extra keyword arguments straight to the `ValidationError`
template context, and `retarget` sets an `HX-Retarget` header so htmx swaps errors
into a different element than the trigger.

```python
result = await form_or_errors(
    request, TaskForm, "board.html", "add_form",
    retarget="#errors",   # optional HX-Retarget header
    columns=COLUMNS,      # extra template context for the re-render
)
```

## Built-in validation rules

Import rules from `chirp.validation`. Each returns an error message string on
failure or `None` on success.

:::{list-table}
:header-rows: 1

* - Rule
  - Field must…
* - `required`
  - be present and non-empty (`"0"` counts as present)
* - `min_length(n)` / `max_length(n)`
  - be at least / at most *n* characters
* - `email`
  - match a basic email structure
* - `url`
  - be an `http`/`https` URL
* - `matches(pattern, message=None)`
  - match a regex pattern
* - `one_of(*choices)`
  - be one of the given choices
* - `integer` / `number`
  - parse as a whole number / any number
:::

### Custom rules

A rule is any callable returning an error string or `None`. Attach it the same way
as a built-in:

```python
def positive(value: str) -> str | None:
    try:
        if float(value) <= 0:
            return "Must be a positive number"
    except ValueError:
        return "Must be a number"
    return None


@dataclass(frozen=True, slots=True)
class PaymentForm:
    amount: Annotated[str, required, positive]
```

## File uploads

Multipart forms expose uploaded files via `form.files`. Read the bytes, or stream
to disk with `save()` (which sanitizes the destination basename against path
traversal).

```python
@app.route("/upload", methods=["POST"])
async def upload(request: Request):
    form = await request.form()
    avatar = form.files.get("avatar")  # UploadFile or None
    if avatar is not None:
        await avatar.save(UPLOAD_DIR / avatar.filename)
    return FormAction("/profile")
```

:::{note}
Multipart parsing needs the `forms` extra: `pip install bengal-chirp[forms]`.
URL-encoded forms (the default for non-file submissions) need no extra.
:::

## Form-field macros

Chirp ships Kida macros for labelled fields with automatic error display. They read
the same `errors` dict that `ValidationError` carries, add a `field--error` class to
the wrapper, and emit `<span class="field-error">` plus ARIA attributes
(`aria-invalid`, `aria-describedby`, `aria-required`) when a field has messages.

```html
{% from "chirp/forms.html" import text_field, textarea_field %}

<form hx-post="/tasks" hx-target="#task_form" hx-swap="outerHTML">
    {{ text_field("title", form.title ?? "", label="Title",
                  errors=errors, required=true) }}
    {{ textarea_field("description", form.description ?? "",
                      label="Description", errors=errors) }}
    <button type="submit">Create</button>
</form>
```

:::{list-table}
:header-rows: 1

* - Macro
  - Renders
* - `text_field(name, value, label, errors, type, required, placeholder, attrs)`
  - Text input — set `type` for `password`, `email`, etc.
* - `textarea_field(name, value, label, errors, rows, required, placeholder)`
  - Multi-line text
* - `select_field(name, options, selected, label, errors, required)`
  - Dropdown — each option needs `.value` and `.label`
* - `checkbox_field(name, checked, label, errors)`
  - Checkbox with label
* - `hidden_field(name, value)`
  - Hidden input
:::

## Gotchas

:::{warning}
`validate()` takes a **`Mapping`** (a `FormData` instance or a plain `dict`) of
field names to strings — not a dataclass instance. It calls `data.get(...)`, which
a frozen dataclass does not have. When you have a bound dataclass and need to
re-run validation, convert it first with `form_values(instance)`, or pass the raw
`await request.form()` mapping.
:::

## Advanced & alternate flows

The happy path above covers most forms. Open these when you need the lower-level
pieces.

:::{dropdown} Lower-level: form_from() and manual error handling
`form_or_errors()` wraps `form_from()` plus a `try`/`except`. Use `form_from()`
directly when you want the raw `FormBindingError.errors` dict — for example to
log it, merge it with other errors, or branch on specific fields before
re-rendering.

```python
from chirp import form_from, FormBindingError, ValidationError

@app.route("/tasks", methods=["POST"])
async def add_task(request: Request):
    try:
        form = await form_from(request, TaskForm)
    except FormBindingError as e:
        # e.errors is dict[str, list[str]]
        return ValidationError("tasks.html", "task_form", errors=e.errors)

    # form.title, form.description are populated
    save_task(form.title, form.description)
    return FormAction("/tasks")
```

`form_from()` runs binding and type coercion only — it does **not** run `Annotated`
rules. Use `form_or_errors()` if you want declarative rules.
:::{/dropdown}

:::{dropdown} Manual validation without a dataclass (validate / ValidationResult)
When you are not binding to a dataclass — validating raw query params, a partial
sub-form, or data assembled by hand — call the module-level `validate(data, rules)`.
It returns a `ValidationResult` that is falsy when invalid, so the pattern is
`if not result:`.

```python
from chirp import Request, Redirect, ValidationError
from chirp.validation import validate, required, min_length, email

@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()

    result = validate(form, {
        "name": [required, min_length(2)],
        "email": [required, email],
        "password": [required, min_length(8)],
    })
    if not result:
        return ValidationError("register.html", "form_errors",
            errors=result.errors,
            form=form,
        )

    create_user(result.data)  # result.data holds the cleaned values
    return Redirect("/welcome")
```

`ValidationResult` is a frozen dataclass with `.data` (cleaned values), `.errors`
(field → list of messages), and `.is_valid`. There is no `.check()` method —
collect every field's rules into the dict you pass to `validate()`.
:::{/dropdown}

:::{dropdown} Re-populating after business validation
When binding succeeds but a *business* rule fails (duplicate email, insufficient
balance), use `form_values()` to turn the bound instance back into a
`dict[str, str]` for the re-rendered form. It also accepts a `Mapping`; `None`
becomes `""`.

```python
from chirp import form_values, ValidationError

errors = check_business_rules(result)  # bound instance
if errors:
    return ValidationError(
        "tasks.html", "task_form",
        errors=errors,
        form=form_values(result),  # {"title": "...", "description": "...", ...}
    )
```
:::{/dropdown}

:::{note} See also
- [[docs/about/core-concepts/return-values|Return Values]] — the full `ValidationError` and `FormAction` API and negotiation rules.
- [[docs/build-apps/forms-data/shapes|Shapes]] — the frozen-dataclass data layer your form can write into.
- [[docs/build-apps/html-fragments/fragments|Fragments]] — targeting the form fragment with htmx.
:::

:::{related}
:::
## Experimental WebMCP form projection

An existing typed form can opt into the declarative WebMCP preview while
keeping its normal browser and htmx submission path:

```python
from dataclasses import dataclass, field

from chirp import WebMCPForm
from chirp.contracts import FormContract, contract

@dataclass(frozen=True, slots=True)
class SearchForm:
    query: str = field(metadata={
        "webmcp_control": "search",
        "webmcp_description": "Words to search for",
        "webmcp_min_length": 2,
    })

@app.route("/search", methods=["POST"])
@contract(form=FormContract(
    SearchForm,
    "search.html",
    "search_form",
    webmcp=WebMCPForm("search.run", "Search the catalog"),
))
async def search(request):
    form = await form_from(request, SearchForm)
    ...
```

```html
<form method="post" action="/search"{{ webmcp_form_attrs("search.run") }}>
  {{ csrf_field() }}
  <input{{ webmcp_control_attrs("search.run", "query") }}>
  <button type="submit">Search</button>
</form>
```

The helpers emit escaped `toolname`, `tooldescription`,
`toolparamdescription`, and native input attributes from the frozen contract.
They do not register JavaScript tools or bypass the server. Mutation forms
cannot enable `toolautosubmit`, unsupported controls fail during startup, and
browsers without WebMCP continue to use the same complete form.

`app.check()` reports malformed or duplicate operation metadata, control/helper
drift, missing native submission fallback, missing route/template/block, and
mutation CSRF/security gaps as `webmcp` ERRORs. Each error names the operation
and source location plus the concrete repair; there are no WebMCP style-only
warnings. Run `chirp check myapp:app --json --coverage` to include declared and
compiled projection/parameter counters in CI baselines and contract diffs.

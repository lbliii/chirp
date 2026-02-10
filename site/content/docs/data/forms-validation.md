---
title: Forms & Validation
description: Form parsing, multipart uploads, and validation
draft: false
weight: 20
lang: en
type: doc
tags: [forms, validation, multipart]
keywords: [forms, validation, multipart, file-upload, validation-result, rules, form-from, form-or-errors, form-values, form-macros, dataclass-binding]
category: guide
---

## Parsing Forms

Access form data from POST requests:

```python
@app.route("/submit", methods=["POST"])
async def submit(request: Request):
    form = await request.form()
    name = form.get("name", "")
    email = form.get("email", "")
    # ... process form data
```

:::{note}
Multipart form parsing requires the `forms` extra: `pip install bengal-chirp[forms]`. URL-encoded forms work without extras.
:::

## File Uploads

For multipart forms with file uploads:

```python
@app.route("/upload", methods=["POST"])
async def upload(request: Request):
    form = await request.form()
    file = form["avatar"]
    content = await file.read()
    filename = file.filename
    # ... save file
```

## Dataclass Binding

`form_from()` binds form data to a frozen dataclass. Define the shape, and Chirp handles type coercion for `str`, `int`, `float`, and `bool`:

```python
from dataclasses import dataclass
from chirp import form_from, FormBindingError

@dataclass(frozen=True, slots=True)
class TaskForm:
    title: str
    description: str = ""
    priority: str = "medium"

@app.route("/tasks", methods=["POST"])
async def add_task(request: Request):
    try:
        form = await form_from(request, TaskForm)
    except FormBindingError as e:
        # e.errors is dict[str, list[str]]
        return ValidationError("tasks.html", "form", errors=e.errors)

    # form.title, form.description, form.priority are populated
```

Fields without defaults are required — if missing, `FormBindingError` is raised with structured errors.

## Bind or Error

`form_or_errors()` combines `form_from()` and `ValidationError` into a single call, eliminating the try/except boilerplate:

```python
from chirp import form_or_errors, ValidationError

@app.route("/tasks", methods=["POST"])
async def add_task(request: Request):
    result = await form_or_errors(request, TaskForm, "tasks.html", "task_form")
    if isinstance(result, ValidationError):
        return result

    # result is TaskForm — proceed with business logic
    save_task(result.title, result.description)
```

On binding failure, it returns a `ValidationError` pre-loaded with the errors and the raw form values for re-population. Extra template context is passed through:

```python
result = await form_or_errors(
    request, TaskForm, "board.html", "add_form",
    retarget="#errors",   # optional HX-Retarget header
    columns=COLUMNS,      # extra template context
)
```

## Re-populating Forms

When validation fails, use `form_values()` to convert a dataclass back to a `dict[str, str]` for template re-population:

```python
from chirp import form_values

# After binding succeeds but business validation fails:
errors = validate_task(result)
if errors:
    return ValidationError(
        "tasks.html", "task_form",
        errors=errors,
        form=form_values(result),  # {"title": "...", "description": "...", ...}
    )
```

`form_values()` also accepts a `Mapping` (dict, `FormData`, etc.) and converts all values to strings. `None` becomes `""`.

## Form Field Macros

Chirp ships template macros for common form fields. Import them from `chirp/forms.html`:

```html
{% from "chirp/forms.html" import text_field, textarea_field, select_field %}

<form hx-post="/tasks" hx-target="#task-form">
    {{ text_field("title", form.title ?? "", label="Title",
                  errors=errors, required=true) }}
    {{ textarea_field("description", form.description ?? "",
                      label="Description", errors=errors) }}
    <button type="submit">Create</button>
</form>
```

Each macro renders a labelled field with automatic error display. When `errors` contains messages for that field, a `field--error` CSS class is added and `<span class="field-error">` elements are rendered.

Available macros:

| Macro | Description |
|-------|-------------|
| `text_field(name, value, label, errors, type, required, placeholder, attrs)` | Text input (also works for `password`, `email`, etc. via `type`) |
| `textarea_field(name, value, label, errors, rows, required, placeholder)` | Multi-line text |
| `select_field(name, options, selected, label, errors, required)` | Dropdown (options need `.value` and `.label`) |
| `checkbox_field(name, checked, label, errors)` | Checkbox with label |
| `hidden_field(name, value)` | Hidden input |

The macros work with the `field_errors` filter and the errors dict shape from `FormBindingError` and `ValidationResult`.

## Validation

Chirp includes a validation module for checking form data:

```python
from chirp.validation import ValidationResult
from chirp.validation.rules import required, min_length, email

@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()

    result = ValidationResult()
    result.check("name", form.get("name", ""), [required, min_length(2)])
    result.check("email", form.get("email", ""), [required, email])
    result.check("password", form.get("password", ""), [required, min_length(8)])

    if not result.is_valid:
        return ValidationError("register.html", "form_errors",
            errors=result.errors,
            form=form,
        )

    # ... create user
    return Redirect("/welcome")
```

## Validation Rules

Built-in validation rules:

| Rule | Description |
|------|-------------|
| `required` | Field must not be empty |
| `min_length(n)` | Minimum string length |
| `max_length(n)` | Maximum string length |
| `email` | Valid email format |
| `matches(pattern)` | Regex pattern match |

### Custom Rules

A validation rule is any callable that returns an error string or `None`:

```python
def must_be_positive(value: str) -> str | None:
    try:
        if float(value) <= 0:
            return "Must be a positive number"
    except ValueError:
        return "Must be a number"
    return None

result.check("amount", form.get("amount", ""), [required, must_be_positive])
```

## ValidationError Return Type

`ValidationError` renders a fragment with a 422 status code, designed for htmx form error handling:

```python
return ValidationError("register.html", "form_errors",
    errors=result.errors,
    form=form,
)
```

The template:

```html
{% block form_errors %}
  <div id="errors" class="error-list">
    {% for field, messages in errors.items() %}
      {% for msg in messages %}
        <p class="error">{{ field }}: {{ msg }}</p>
      {% endfor %}
    {% endfor %}
  </div>
{% endblock %}
```

With htmx, you can target the error block specifically:

```html
<form hx-post="/register" hx-target="#errors" hx-swap="outerHTML">
  <input name="name" placeholder="Name">
  <input name="email" placeholder="Email">
  <input name="password" type="password" placeholder="Password">
  <button type="submit">Register</button>
  <div id="errors"></div>
</form>
```

## Next Steps

- [[docs/data/database|Database]] -- Async database access
- [[docs/templates/fragments|Fragments]] -- Fragment rendering for forms
- [[docs/core-concepts/return-values|Return Values]] -- ValidationError and other types

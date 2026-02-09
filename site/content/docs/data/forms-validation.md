---
title: Forms & Validation
description: Form parsing, multipart uploads, and validation
draft: false
weight: 20
lang: en
type: doc
tags: [forms, validation, multipart]
keywords: [forms, validation, multipart, file-upload, validation-result, rules]
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

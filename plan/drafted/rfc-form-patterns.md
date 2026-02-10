# RFC: Form Handling Patterns

**Status**: Draft  
**Date**: 2026-02-10  
**Scope**: `chirp.http.forms`, `chirp.templating.filters`, template macros  
**Related**: Gap Analysis — Kida/Chirp Strategic Plan

---

## Problem

Chirp has the primitives — `form_from()` for dataclass binding, `FormBindingError`
for binding failures, `ValidationError` for htmx error rendering, and
`field_errors` filter for template-side error display. But connecting them
requires boilerplate that every form handler repeats:

```python
@app.route("/tasks", methods=["POST"])
@login_required
async def add_task(request: Request):
    f = await form_from(request, TaskForm)
    assignee = f.assignee or get_user().name
    tags = tuple(t.strip() for t in f.tags.split(",") if t.strip())

    errors = _validate_task(f.title, f.status, f.priority)
    if errors:
        return ValidationError(
            "board.html",
            "add_form",
            errors=errors,
            columns=COLUMNS,
            form={"title": f.title, "description": f.description, ...},
        )
```

### Evidence

**`form_from()` raises on binding errors** (`src/chirp/http/forms.py:134-206`):
It raises `FormBindingError` with a dict of errors. But `ValidationError` is
returned, not raised. Every handler needs a try/except bridge:

```python
try:
    form = await form_from(request, TaskForm)
except FormBindingError as e:
    return ValidationError("form.html", "form_body", errors=e.errors)
```

**Re-populating form values is manual** (`examples/kanban/app.py:510-513`):
When validation fails, the handler must manually reconstruct a `form` dict from
the dataclass fields to re-populate the template. This is error-prone and
verbose.

**No template macros for form fields**: Every project writes its own
`<input>` + `<label>` + error display patterns. The `field_errors` filter
exists but field rendering is entirely manual.

### What's Already Good

- `form_from()` with dataclass binding and type coercion is solid
- `FormBindingError` with structured `{field: [messages]}` is the right shape
- `ValidationError` with htmx retarget support works well
- `field_errors` filter is clean and safe

The gap is **glue** — connecting these pieces without boilerplate.

---

## Goals

1. Reduce form handler boilerplate for the bind → validate → error path.
2. Ship template macros for common form field patterns.
3. Maintain Chirp's philosophy: no magic, no base classes, explicit control.

### Non-Goals

- Validation framework (Chirp provides binding, not validation).
- Form class hierarchy (use frozen dataclasses).
- JavaScript-side validation (server-side only).
- CSRF token injection (already handled by `CSRFMiddleware`).

---

## Design

### 1. `form_or_errors()` — The Glue Function

A convenience function that bridges `form_from()` and `ValidationError`:

```python
# src/chirp/http/forms.py

async def form_or_errors[T](
    request: Any,
    datacls: type[T],
    template_name: str,
    block_name: str,
    /,
    *,
    retarget: str | None = None,
    **extra_context: Any,
) -> T | ValidationError:
    """Bind form data or return a ValidationError for re-rendering.

    Combines ``form_from()`` and ``ValidationError`` into a single call.
    On success, returns the populated dataclass. On binding failure,
    returns a ``ValidationError`` with the errors and the raw form values
    for re-population.

    Usage::

        result = await form_or_errors(request, TaskForm, "tasks.html", "form")
        if isinstance(result, ValidationError):
            return result
        # result is TaskForm — proceed with validated data
    """
    try:
        return await form_from(request, datacls)
    except FormBindingError as e:
        form_data = await request.form()
        return ValidationError(
            template_name,
            block_name,
            retarget=retarget,
            errors=e.errors,
            form=dict(form_data),
            **extra_context,
        )
```

This is *not* magic — it's a transparent composition of existing primitives.
The caller still controls the template name, block name, and extra context.
The return type is `T | ValidationError`, which the type checker understands.

**Usage in a handler:**

```python
@app.route("/tasks", methods=["POST"])
async def add_task(request: Request) -> Page | ValidationError:
    result = await form_or_errors(request, TaskForm, "tasks.html", "task_form")
    if isinstance(result, ValidationError):
        return result

    # result is TaskForm — business validation
    errors = validate_task(result)
    if errors:
        return ValidationError("tasks.html", "task_form",
                               errors=errors, form=result)
    ...
```

### 2. Form Re-population Via Dataclass

When `ValidationError` is returned, the template needs the form values to
re-populate inputs. Currently this requires manually constructing a dict
(`examples/kanban/app.py:510-513`).

Add a `form_values()` utility that converts a dataclass or `FormData` to a
template-friendly dict:

```python
def form_values(form: Any) -> dict[str, str]:
    """Extract form field values as strings for template re-population.

    Accepts a dataclass instance or a FormData mapping.
    """
    if hasattr(form, "__dataclass_fields__"):
        from dataclasses import asdict
        return {k: str(v) if v is not None else "" for k, v in asdict(form).items()}
    if isinstance(form, Mapping):
        return {k: str(v) for k, v in form.items()}
    return {}
```

### 3. Template Macros for Form Fields

Ship a set of Kida template macros as includable templates in
`src/chirp/templating/macros/forms.html`:

```html
{# Text input with label and error display #}
{% def text_field(name, value="", label=None, errors=None, type="text",
                  required=False, placeholder="", attrs="") %}
    <div class="field{% if errors | field_errors(name) %} field--error{% end %}">
        {% if label %}
            <label for="{{ name }}">{{ label }}</label>
        {% end %}
        <input type="{{ type }}" id="{{ name }}" name="{{ name }}"
               value="{{ value }}"
               {% if required %}required{% end %}
               {% if placeholder %}placeholder="{{ placeholder }}"{% end %}
               {{ attrs }}>
        {% for msg in errors | field_errors(name) %}
            <span class="field-error">{{ msg }}</span>
        {% end %}
    </div>
{% end %}

{# Textarea with label and error display #}
{% def textarea_field(name, value="", label=None, errors=None,
                      rows=4, required=False, placeholder="") %}
    <div class="field{% if errors | field_errors(name) %} field--error{% end %}">
        {% if label %}
            <label for="{{ name }}">{{ label }}</label>
        {% end %}
        <textarea id="{{ name }}" name="{{ name }}" rows="{{ rows }}"
                  {% if required %}required{% end %}
                  {% if placeholder %}placeholder="{{ placeholder }}"{% end %}>{{ value }}</textarea>
        {% for msg in errors | field_errors(name) %}
            <span class="field-error">{{ msg }}</span>
        {% end %}
    </div>
{% end %}

{# Select dropdown with label and error display #}
{% def select_field(name, options, selected="", label=None, errors=None,
                    required=False) %}
    <div class="field{% if errors | field_errors(name) %} field--error{% end %}">
        {% if label %}
            <label for="{{ name }}">{{ label }}</label>
        {% end %}
        <select id="{{ name }}" name="{{ name }}"
                {% if required %}required{% end %}>
            {% for opt in options %}
                <option value="{{ opt.value }}"
                        {% if opt.value == selected %}selected{% end %}>
                    {{ opt.label }}
                </option>
            {% end %}
        {% end %}
        {% for msg in errors | field_errors(name) %}
            <span class="field-error">{{ msg }}</span>
        {% end %}
    </div>
{% end %}

{# Checkbox #}
{% def checkbox_field(name, checked=False, label=None, errors=None) %}
    <div class="field{% if errors | field_errors(name) %} field--error{% end %}">
        <label>
            <input type="checkbox" id="{{ name }}" name="{{ name }}"
                   {% if checked %}checked{% end %}>
            {{ label ?? name }}
        </label>
        {% for msg in errors | field_errors(name) %}
            <span class="field-error">{{ msg }}</span>
        {% end %}
    </div>
{% end %}

{# Hidden field #}
{% def hidden_field(name, value="") %}
    <input type="hidden" name="{{ name }}" value="{{ value }}">
{% end %}
```

Usage in application templates:

```html
{% from "chirp/forms" import text_field, textarea_field, select_field %}

<form hx-post="/tasks" hx-target="#task-form">
    {{ text_field("title", form.title ?? "", label="Title",
                  errors=errors, required=True) }}
    {{ textarea_field("description", form.description ?? "",
                      label="Description", errors=errors) }}
    <button type="submit">Create</button>
</form>
```

### Macro Registration

The macros are shipped as a Kida template file. Chirp's environment setup
(`src/chirp/templating/integration.py:18-47`) adds a `PackageLoader` for
`chirp.templating.macros` alongside the user's `FileSystemLoader`:

```python
from kida import ChoiceLoader, FileSystemLoader, PackageLoader

loader = ChoiceLoader([
    FileSystemLoader(template_dir),
    PackageLoader("chirp.templating", "macros"),  # chirp/forms.html etc.
])
```

This makes `{% from "chirp/forms" import text_field %}` work without any
user configuration.

---

## Testing Strategy

1. **`form_or_errors()` tests**: Success path returns dataclass, failure path
   returns `ValidationError` with correct errors and form values.
2. **`form_values()` tests**: Handles dataclass, FormData, and edge cases.
3. **Template macro tests**: Render each macro with various inputs, verify
   HTML output, error display, and CSS classes.
4. **Integration tests**: Full POST → bind → validate → error → re-render cycle.

---

## Future Considerations

1. **Contract validation**: `app.check()` could verify that form fields in
   templates match dataclass fields (see Gap 6 RFC).
2. **File upload macros**: `file_field()` macro with `UploadFile` support.
3. **Multi-value fields**: `checkbox_group()`, `multi_select()` macros.
4. **ARIA attributes**: Accessibility-first form macros with `aria-invalid`,
   `aria-describedby` for screen readers.

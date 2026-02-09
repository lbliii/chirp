---
title: Filters
description: Register custom template filters and globals
draft: false
weight: 30
lang: en
type: doc
tags: [templates, filters, globals, kida]
keywords: [filter, global, template-filter, template-global, jinja, kida]
category: guide
---

## Built-in Filters

Chirp ships with built-in filters that are automatically available in every template. These complement Kida's core filters with web-specific utilities.

### field_errors

Extract validation errors for a single form field from an errors dict. Returns a list of error messages.

```html
{% for msg in errors | field_errors("email") %}
    <p class="error">{{ msg }}</p>
{% end %}
```

If the field has no errors, or `errors` is `None`, an empty list is returned — so the loop simply produces nothing.

Typical usage with `form_from()`:

```python
@app.route("/signup", methods=["POST"])
async def signup(request: Request) -> Template | Fragment:
    data, errors = await form_from(request, SignupForm)
    if errors:
        return Template("signup.html", errors=errors)
    # ... process valid data
```

```html
<label>Email</label>
<input name="email" value="{{ data.email | default('') }}">
{% for msg in errors | field_errors("email") %}
    <span class="field-error">{{ msg }}</span>
{% end %}
```

### qs

Build a URL with query-string parameters. Falsy values are automatically omitted.

```html
<a href="{{ '/search' | qs(q=query, page=page) }}">Search</a>
{# Output: /search?q=hello&page=2 #}
```

Falsy values (`None`, `""`, `0`, `False`) are dropped:

```html
{{ '/items' | qs(q=query, category=category, page=none) }}
{# If category is "", outputs: /items?q=hello #}
```

Appends to existing query strings:

```html
{{ '/search?q=hello' | qs(page=2) }}
{# Output: /search?q=hello&page=2 #}
```

Special characters are URL-encoded:

```html
{{ '/search' | qs(q="hello world") }}
{# Output: /search?q=hello%20world #}
```

---

## Custom Filters

Filters transform values in templates. Register them with `@app.template_filter()`:

```python
@app.template_filter()
def currency(value: float) -> str:
    return f"${value:,.2f}"

@app.template_filter()
def pluralize(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural
```

Use them in templates with the pipe syntax:

```html
<span class="price">{{ product.price | currency }}</span>
<span>{{ count }} {{ count | pluralize("item", "items") }}</span>
```

## Named Filters

By default, the function name becomes the filter name. Override it with an argument:

```python
@app.template_filter("fmt_date")
def format_date(dt: datetime) -> str:
    return dt.strftime("%B %d, %Y")
```

```html
<time>{{ post.created_at | fmt_date }}</time>
```

## Template Globals

Globals are functions or values available in every template without being passed in the context:

```python
@app.template_global()
def site_name() -> str:
    return "My App"

@app.template_global()
def current_year() -> int:
    return datetime.now().year
```

```html
<footer>&copy; {{ current_year() }} {{ site_name() }}</footer>
```

## Registration Timing

Filters and globals must be registered during the setup phase (before `app.run()` or the first request). They become part of the kida environment at freeze time.

```python
app = App()

# Register during setup
@app.template_filter()
def upper(value: str) -> str:
    return value.upper()

# This works
app.run()

# Registering after freeze would raise an error
```

## Type Safety

Filters are regular Python functions with full type annotations. Your IDE provides autocomplete and type checking for filter arguments.

```python
@app.template_filter()
def truncate(value: str, length: int = 50, suffix: str = "...") -> str:
    if len(value) <= length:
        return value
    return value[:length].rsplit(" ", 1)[0] + suffix
```

## Next Steps

- [[docs/templates/rendering|Rendering]] -- How templates are rendered
- [[docs/core-concepts/app-lifecycle|App Lifecycle]] -- When filters are registered
- [[docs/reference/api|API Reference]] -- Complete API surface

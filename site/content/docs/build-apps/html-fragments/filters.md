---
title: Filters & Globals
description: Register custom template filters and globals, and use Chirp's web-specific built-ins
draft: false
weight: 30
lang: en
type: doc
tags: [templates, filters, globals, kida]
keywords: [filter, global, template-filter, template-global, kida, template-engine]
category: guide
---

A **filter** transforms a value inside a template with the pipe syntax — `{{ value | filter }}`. A **global** is a function or value available in every template without passing it through the route's context. Chirp ships a handful of web-specific built-in filters and globals, and lets you register your own with `@app.template_filter()` and `@app.template_global()`.

## Register a custom filter

Decorate a function with `@app.template_filter()`. The function name becomes the filter name, and the piped value is the first argument:

```python
from chirp import App

app = App()

@app.template_filter()
def currency(value: float) -> str:
    return f"${value:,.2f}"
```

Use it in a template with the pipe:

```html
<span class="price">{{ product.price | currency }}</span>
{# → <span class="price">$1,299.00</span> #}
```

Extra arguments after the piped value are passed in the parentheses:

```python
@app.template_filter()
def excerpt(value: str, length: int = 50, suffix: str = "...") -> str:
    if len(value) <= length:
        return value
    return value[:length].rsplit(" ", 1)[0] + suffix
```

```html
<p>{{ post.body | excerpt(120) }}</p>
```

Filters are ordinary Python functions, so your type annotations give your IDE autocomplete and type-checking on the arguments.

:::{note}
Register filters and globals during setup, before `app.run()` (or `app.freeze()`). They become part of the template environment when the app freezes; registering after that raises `RuntimeError`.
:::

## Common patterns

### Named filters

By default the function name is the filter name. Pass a string to override it — useful when the Python name and the template name should differ:

```python
@app.template_filter("type_color")
def type_color(type_name: str) -> str:
    """Return the CSS color for a Pokemon type."""
    return TYPE_COLORS.get(type_name.lower(), "#777")


@app.template_filter("sprite")
def sprite_url(pokemon_id: int, variant: str = "default") -> str:
    """Return the PokeAPI sprite URL for a Pokemon ID."""
    if variant == "artwork":
        return f"{SPRITE_BASE}/other/official-artwork/{pokemon_id}.png"
    return f"{SPRITE_BASE}/{pokemon_id}.png"
```

*Source: [`examples/standalone/pokedex/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/pokedex/app.py).*

```html
<span style="color: {{ pokemon.type | type_color }}">{{ pokemon.type }}</span>
<img src="{{ pokemon.id | sprite('artwork') }}" alt="{{ pokemon.name }}">
```

:::{warning}
A custom filter that reuses a built-in name (such as `pluralize`) overrides the built-in for your whole app. Pick a distinct name unless you mean to replace it.
:::

### Template globals

Globals are functions or values callable from any template without being passed in the route context:

```python
from datetime import datetime

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

Like filters, globals take an optional name argument: `@app.template_global("year")`.

## Built-in filters

Chirp registers these web-specific filters on every template environment — no import or registration needed. They complement the filters that come from [[docs/build-apps/html-fragments/kida-integration|Kida, the template engine]].

:::{list-table} Built-in filters
:header-rows: 1

* - Filter
  - Does
  - Example
* - `field_errors`
  - Returns the list of validation messages for one form field, or an empty list when there are none.
  - `{% for m in errors | field_errors("email") %}…{% end %}`
* - `qs`
  - Builds a query string on a URL path. Falsy values (`None`, `""`, `0`, `False`) are dropped.
  - `{{ '/search' | qs(q=query, page=page) }}` → `/search?q=hello&page=2`
* - `attr`
  - Emits an HTML attribute only when the value is truthy, else nothing. The value is HTML-escaped.
  - `<a href="/x"{{ cls | attr("class") }}>` → ` class="active"` when `cls` is truthy
* - `url`
  - Safelists a URL for an `href`: returns it when the scheme is safe (`http`, `https`, relative), else a fallback (default `#`). Use on user or external data.
  - `<a href="{{ link | url(fallback='/') }}">`
:::

`field_errors` pairs with the errors dict returned by [[docs/build-apps/forms-data/forms-validation|form validation]]:

```html
<label>Email</label>
<input name="email" value="{{ form.email ?? "" }}">
{% for msg in errors | field_errors("email") %}
    <span class="field-error">{{ msg }}</span>
{% end %}
```

:::{dropdown} Island filters (advanced)
For [[docs/build-apps/ui-extensions/islands|island mount attributes]], Chirp also ships the `island_props` filter plus the `island_attrs` and `primitive_attrs` globals. Reach for these only when mounting a client-side island.

`island_props` serializes a value to HTML-escaped JSON for a `data-island-props` attribute:

```html
<div data-island="editor" data-island-props="{{ state | island_props }}">
  Fallback editor UI.
</div>
```

The `island_attrs` global builds the full mount attribute string in one call:

```html
<div{{ island_attrs("editor", props=state, mount_id="editor-root") }}>
  Fallback editor UI.
</div>
```

Use `primitive_attrs` when the mount needs stricter primitive metadata:

```html
<div{{ primitive_attrs("grid_state", props={"stateKey": "team", "columns": ["name", "role"]}) }}>
  ...
</div>
```
:::{/dropdown}

## Escaping and the `safe` filter

When `AppConfig(autoescape=True)` (the default), `{{ x }}` is HTML-escaped automatically — the main defense against XSS. The escaping filters come from Kida: use `| e` (or `| escape`) to escape explicitly when chaining filters that might drop escaping, and `| safe(reason="...")` to mark output as trusted HTML so it is *not* escaped.

:::{danger}
Never pipe raw user input through `safe`. Marking unescaped, user-controlled HTML as safe is a direct XSS vulnerability. Use `safe` only on content you have sanitized or that comes from a trusted source (sanitized markdown, server-generated HTML).

```html
{{ cms_block | safe(reason="admin-only CMS") }}   {# OK: trusted source #}
```

The `reason` argument is for code review and audit only — it has no runtime effect.
:::

To render markdown, register the `markdown` filter once during setup. It sanitizes unsafe HTML and URLs by default; pass `sanitize=False` only for fully trusted markdown:

```python
from chirp.markdown import register_markdown_filter

register_markdown_filter(app)   # adds the `markdown` filter
```

```html
{{ post.body | markdown }}
```

:::{note} See also
- [[docs/build-apps/html-fragments/kida-integration|Kida template integration]] — escaping rules and context-specific escaping (JavaScript, CSS) for `href`, scripts, and styles.
- [[docs/quality/contracts-debugging/route-contract|The route contract checks]] — how `chirp check` validates that `hx-*` and `action` URLs resolve to registered routes.
:::

## Next steps

- [[docs/build-apps/html-fragments/rendering|Rendering]] — how a template is rendered into a response
- [[docs/about/core-concepts/app-lifecycle|App lifecycle]] — when filters and globals are frozen into the environment
- [[docs/reference/api|API reference]] — the complete API surface

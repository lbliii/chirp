---
title: Routing
order: 2
category: Getting Started
description: How URL routing works in Chirp.
---
# Routing

Routes map URLs to handler functions using decorators:

```python
@app.route("/contacts")
def list_contacts():
    return [{"id": 1, "name": "Alice"}]
```

## Path Parameters

Use `{name:type}` syntax for dynamic segments:

```python
@app.route("/contacts/{contact_id:int}")
def get_contact(contact_id: int):
    return {"id": contact_id, "name": "Alice"}
```

Supported types: `str` (default), `int`, `float`, `path`.

## HTTP Methods

```python
@app.route("/contacts", methods=["POST"])
def create_contact(request):
    return {"status": "created"}
```

## What Autodoc Captures

When `autodoc=True`, every route registered with `@app.route()` is
introspected after freeze. The generated reference includes:

- Path and methods
- Handler docstring
- Parameter names and types
- Template name (if any)

Check the **API Reference** section in the sidebar to see the
auto-generated pages for this app's routes.

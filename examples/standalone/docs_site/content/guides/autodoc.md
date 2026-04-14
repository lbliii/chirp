---
title: Autodoc
order: 2
category: Guides
description: Auto-generated API reference from frozen app state.
---
# Autodoc

When `DocsPlugin(autodoc=True)`, Chirp introspects the frozen app
and generates API reference pages automatically.

## What Gets Documented

| Source | Captured Fields |
|--------|----------------|
| Routes | path, methods, handler docstring, parameters, template |
| Tools | name, description, input schema, parameters |

## Slug Namespace

Autodoc pages live under `api/` to avoid collision with hand-written docs:

- `/docs/api/routes/contacts` — the `GET /contacts` route
- `/docs/api/tools/echo` — the `echo` tool

## The Pipeline

1. `DocsPlugin.register()` adds a startup hook
2. After `app.freeze()`, the hook calls `generate_autodoc(app)`
3. Route and tool introspection produces `DocPage` instances
4. Pages merge into the main `DocsCollection`
5. Everything is searchable and navigable together

## Contract Checks

`app.check()` validates docs integrity at startup:

- All `.md` files parse successfully
- No duplicate slugs across markdown and autodoc
- Internal cross-references resolve
- Draft pages not exposed in production

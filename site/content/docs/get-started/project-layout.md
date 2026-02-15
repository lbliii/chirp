---
title: Project Layout
description: Recommended directory structure for Chirp apps
draft: false
weight: 20
lang: en
type: doc
tags: [getting-started, layout, structure, conventions]
keywords: [project, layout, structure, templates, static]
category: onboarding
---

## Recommended Structure

Chirp does not enforce a specific layout. This is the convention used by `chirp new`:

```
myapp/
  app.py              # App instance, routes, entry point
  templates/
    base.html         # Base layout (or extend chirp/layouts/boost.html)
    index.html        # Page templates
  static/
    style.css         # CSS, JS, images
  tests/
    test_app.py       # TestClient tests
```

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `app.py` | App creation, route registration, `if __name__ == "__main__": app.run()` |
| `templates/` | Kida templates. Paths are relative to `AppConfig(template_dir="templates")`. |
| `static/` | CSS, JS, images. Served at `/static` by default. |
| `tests/` | Pytest tests. Use `TestClient(app)` for requests. |

## Optional Layouts

**Minimal** (`chirp new myapp --minimal`):

```
myapp/
  app.py
  templates/
    index.html
```

**With SSE** (`chirp new myapp --sse`):

Adds `EventStream` route, boost layout, and `sse-connect` in the template.

## Customizing

- **Template directory:** `AppConfig(template_dir="pages")`
- **Static directory:** `AppConfig(static_dir="assets")`
- **Component libraries:** `AppConfig(component_dirs=("components",))` for shared partials

## Next Steps

- [[docs/get-started/installation|Installation]] — Install Chirp
- [[docs/get-started/quickstart|Quickstart]] — Build your first app

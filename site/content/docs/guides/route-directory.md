---
title: Route Directory Golden Path
description: The recommended way to structure Chirp route directories for app-shell applications
draft: false
weight: 36
lang: en
type: doc
tags: [routing, app-shell, golden-path, chirp-ui]
keywords: [route directory, _meta.py, sections, app-shell, golden path]
category: guide
---

## The Recommended App Shell Route

A section-member page route with minimal boilerplate:

**`_meta.py`** — declarative metadata:

```python
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Skills", section="discover", breadcrumb_label="Skills", shell_mode="tabbed")
```

**`page.py`** — domain data only:

```python
from chirp import Page
def get():
    return Page("page.html", "content", items=load_items())
```

**`page.html`** — standard blocks:

```html
{% block page_root %}
{% block page_root_inner %}
{% block page_content %}
  {{ items }}
{% end %}
{% end %}
{% end %}
```

No `_context.py` needed when the section provides tabs and breadcrumbs.

## The Recommended Section Setup

Register sections in `app.py` before `mount_pages()`:

```python
from chirp.pages.types import Section, TabItem

app.register_section(Section(
    id="discover",
    label="Discover",
    tab_items=(
        TabItem(label="Skills", href="/skills"),
        TabItem(label="Chains", href="/chains"),
    ),
    breadcrumb_prefix=({"label": "App", "href": "/"},),
))
app.mount_pages("pages")
```

## The Recommended Detail Route

For `{param}/` directories:

**`_meta.py`** — dynamic title:

```python
def meta(name: str) -> RouteMeta:
    return RouteMeta(title=f"Skill: {name}", breadcrumb_label=name)
```

**`_context.py`** — load entity, raise if missing:

```python
from chirp import NotFound
def context(name: str) -> dict:
    skill = store.get(name)
    if not skill:
        raise NotFound()
    return {"skill": skill}
```

**`page.py`** — receives loaded entity from cascade:

```python
def get(skill):
    return Page("page.html", "content", skill=skill)
```

## The Recommended Mutation Route

**`_actions.py`** — `@action` decorated handlers:

```python
from chirp.pages.actions import action

@action("save")
def save(skill_id: str, data: dict):
    update_skill(skill_id, data)
    return {"msg": "saved"}
```

Templates use `_action` form field to dispatch.

## The Recommended Fragment/OOB Pattern

Fragment blocks in `page.html`, OOB regions in layout. Use `shell_actions` in `_context.py` or handler return for shell updates.

## When to Use Each File

| Need | File |
|------|------|
| Route metadata (title, section) | `_meta.py` |
| Inherited context | `_context.py` |
| POST handlers | `_actions.py` |
| Complex view assembly | `_viewmodel.py` |
| Layout wrapper | `_layout.html` |
| Everything else | `page.py` + `page.html` |

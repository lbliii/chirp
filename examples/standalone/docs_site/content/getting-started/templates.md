---
title: Templates
order: 3
category: Getting Started
description: Rendering HTML with Kida templates.
---
# Templates

Chirp uses Kida templates for HTML rendering. Return a `Template` from
your route handler:

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home")
```

## Named Blocks

Templates can define named blocks for fragment rendering:

```python
from chirp import Fragment

@app.route("/search")
def search(request):
    results = find(request.query["q"])
    return Fragment("page.html", "results_block", results=results)
```

## Suspense

Defer heavy content — the shell renders immediately, deferred blocks
stream in via OOB swap:

```python
from chirp import Suspense

@app.route("/dashboard")
def dashboard():
    return Suspense("dashboard.html",
        stats=load_stats(),   # deferred (awaitable)
        title="Dashboard",    # sync (in the shell)
    )
```

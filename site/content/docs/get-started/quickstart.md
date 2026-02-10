---
title: Quickstart
description: Build your first Chirp application in 5 minutes
draft: false
weight: 20
lang: en
type: doc
tags: [quickstart, tutorial]
keywords: [quickstart, hello world, first app, templates, fragments]
category: onboarding
---

## Scaffold a Project

The fastest way to start is the `chirp new` command:

```bash
chirp new myapp
cd myapp
python app.py
```

Open `http://127.0.0.1:8000` in your browser. This generates an `app.py`, a `templates/` directory with `base.html` and `index.html`, a `static/` directory with `style.css`, and a `tests/` directory with a smoke test.

For an even smaller starting point:

```bash
chirp new myapp --minimal
```

This generates only `app.py` and `templates/index.html`.

## Hello World (Manual)

You can also create a project by hand. Create a file called `app.py`:

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

Run it:

```bash
python app.py
```

Open `http://127.0.0.1:8000` in your browser. Five lines to hello world.

## Add Templates

Create a `templates/` directory and add `base.html`:

```html
<!DOCTYPE html>
<html>
<head><title>{{ title }}</title></head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

Add `templates/index.html`:

```html
{% extends "base.html" %}

{% block content %}
  <h1>{{ title }}</h1>
  <p>Welcome to my Chirp app.</p>
{% endblock %}
```

Update `app.py`:

```python
from chirp import App, Template

app = App()

@app.route("/")
def index():
    return Template("index.html", title="Home")

app.run()
```

Route functions return *values*. `Template` tells the framework to render `index.html` with the given context via kida.

## Fragment Rendering

This is where Chirp diverges from Flask. Add a search feature that works as both a full page and an htmx fragment.

Add `templates/search.html`:

```html
{% extends "base.html" %}

{% block content %}
  <h1>Search</h1>
  <input type="search" name="q"
         hx-get="/search" hx-target="#results" hx-trigger="input changed delay:300ms">

  {% block results %}
    <div id="results">
      {% for item in results %}
        <p>{{ item }}</p>
      {% endfor %}
    </div>
  {% endblock %}
{% endblock %}
```

Update `app.py`:

```python
from chirp import App, Template, Fragment, Request

app = App()

ITEMS = ["apple", "banana", "cherry", "date", "elderberry"]

@app.route("/")
def index():
    return Template("index.html", title="Home")

@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    results = [i for i in ITEMS if q.lower() in i.lower()] if q else ITEMS

    if request.is_fragment:
        return Fragment("search.html", "results", results=results)
    return Template("search.html", title="Search", results=results)

app.run()
```

Full page navigation renders everything. An htmx request renders just the `results` block. Same template, same data, different scope.

## Add htmx

To make the fragment rendering work, include htmx in your `base.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <title>{{ title }}</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

Now the search input sends requests to `/search` via htmx, and Chirp responds with just the `results` block -- no full page reload, no separate partials directory, no JavaScript.

## Next Steps

- [[docs/core-concepts/return-values|Return Values]] -- All the types you can return
- [[docs/templates/fragments|Fragments]] -- Deep dive into fragment rendering
- [[docs/streaming/html-streaming|Streaming HTML]] -- Progressive page rendering
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- Real-time updates

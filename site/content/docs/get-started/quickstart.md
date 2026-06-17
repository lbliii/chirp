---
title: Quickstart
description: Go from an empty directory to a running Chirp app with a live search box in about five minutes.
draft: false
weight: 20
lang: en
type: doc
tags: [quickstart, tutorial]
keywords: [quickstart, hello world, first app, templates, fragments]
category: onboarding
---

## What you'll build

Chirp serves HTML over the wire — full pages for browser navigations and HTML
fragments for [[docs/build-apps/html-fragments/fragments|htmx]] requests, both
from one template. This page goes from an empty directory to a running app with
a live search box in about five minutes.

You return values like `Template` and `Page`; the return type tells Chirp what
to render. If you know Flask, the routing will feel familiar — the fragment loop
is the one new idea.

:::{note}
You need [[docs/get-started/installation|Chirp installed]] and Python 3.14+.
:::

## Start a project

You have two ways in. Scaffold a ready-made app with `chirp new`, or build one by
hand to see each piece. Both land on a running app at `http://127.0.0.1:8000`.

:::{tab-set}
:::{tab-item} Scaffold (chirp new)
```bash
chirp new myapp
cd myapp
python app.py
```

The scaffold ships with auth, sessions, CSRF, and security headers already wired.
Log in with `admin` / `password` and open `http://127.0.0.1:8000/dashboard`.
:::{/tab-item}

:::{tab-item} By hand
Create a file called `app.py`:

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

Run it with `python app.py` and open `http://127.0.0.1:8000`. A handler returns
a value; a plain string becomes an HTML response.
:::{/tab-item}
:::{/tab-set}

:::{dropdown} What the scaffold generates (and the secret-key story)
`chirp new myapp` writes an auth-ready layout:

- `app.py` with sessions, auth, CSRF, and security-headers middleware
- `models.py` with a demo user model and password hashing
- `pages/` filesystem routes (`/`, `/login`, `/dashboard`)
- `static/style.css`
- `tests/` with auth-flow tests

For a smaller starting point, `chirp new myapp --minimal` writes a single `app.py`
plus `templates/index.html` — no `pages/` tree, models, or auth routes. The
minimal `app.py` is still not bare: it wires the secure-by-default stack
(`SessionMiddleware` → `CSRFMiddleware` → `SecurityHeadersMiddleware`) and reads
the secret key from `CHIRP_SECRET_KEY`, so even it passes the `security_stack`
contract out of the box.

Every scaffold reads `CHIRP_SECRET_KEY` and refuses to start in production with a
placeholder secret. Generate one before you deploy:

```bash
export CHIRP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

See [[docs/quality/deployment/auth-hardening|auth-hardening]] for the
secure-by-default rationale and [[docs/quality/deployment/production|production config]]
for the full deployment story.
:::

## Add a template

Create a `templates/` directory and add `templates/base.html`:

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

Handlers return values. `Template` tells Chirp to render `index.html` with the
given context through [[docs/build-apps/html-fragments/kida-integration|kida templates]].

## Render a fragment

This is where Chirp diverges from Flask. A search route can serve a full page to
a browser and just the results to an htmx request — from the same template, with
no separate partials directory.

Add `templates/search.html`. Wrap the results in a named block so it can be
rendered on its own:

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

Update `app.py`. Return [[docs/about/core-concepts/return-values|`Page`]] and
Chirp negotiates the response: a full page for browser navigations, the named
block for narrow htmx swaps.

```python
from chirp import App, Template, Page, Request

app = App()

ITEMS = ["apple", "banana", "cherry", "date", "elderberry"]

@app.route("/")
def index():
    return Template("index.html", title="Home")

@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    results = [i for i in ITEMS if q.lower() in i.lower()] if q else ITEMS
    return Page("search.html", "results", title="Search", results=results)

app.run()
```

`Page` replaces the manual `if request.is_htmx: return Fragment(...)` branch you'd
otherwise write on every htmx-reachable route.

:::{dropdown} What `Page` desugars to
`Page("search.html", "results", ...)` is the auto-negotiation form. If you ever
need the branch by hand — to render different blocks per request type, say — read
the request directly:

```python
from chirp import App, Template, Fragment, Request

@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    results = [i for i in ITEMS if q.lower() in i.lower()] if q else ITEMS
    if request.is_htmx:
        return Fragment("search.html", "results", results=results)
    return Template("search.html", title="Search", results=results)
```

Use `request.is_htmx` for any htmx request, or `request.is_narrow_fragment` to
exclude boosted navigations and history restores. Prefer `Page` — it handles all
three cases for you.
:::

## Wire up htmx

To make the fragment swap fire, include htmx in `templates/base.html`:

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

Now the search input sends `hx-get` requests to `/search`, and Chirp responds
with only the `results` block — no full page reload, no separate partials, no
hand-written JavaScript.

## Stream live updates

For updates that arrive *after* the page loads — notifications, a ticker, a live
feed — use [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]].
A route returns an `EventStream` that yields `Fragment` swaps over a long-lived
connection.

::::{steps}
:::{step} Open an SSE scope in your template

Add `templates/feed.html`. Extend the boost layout, wrap the live region in a
named block, and declare where the stream connects:

```html
{% extends "chirp/layouts/boost.html" %}
{% block content %}
  {% block live_block %}
    <ol id="live_block">
      {% for item in items %}
      <li>{{ item }}</li>
      {% endfor %}
    </ol>
  {% endblock %}
{% endblock %}
{% block sse_scope %}
  {% from "chirp/sse.html" import sse_scope %}
  {{ sse_scope("/events", swap="live_block") }}
{% endblock %}
```
:::{/step}

:::{step} Stream fragments from the route

`EventStream` takes an **async** generator. Each `yield` re-renders the
`live_block` from `feed.html` and pushes it down the connection:

```python
from chirp import EventStream, Fragment

@app.route("/events", referenced=True)
async def events():
    async def stream():
        yield Fragment("feed.html", "live_block", items=ITEMS)
    return EventStream(stream())
```
:::{/step}

:::{step} Run chirp check

```bash
chirp check myapp:app
```

This catches SSE scope violations and route/template mismatches before you open
the browser.
:::{/step}
::::{/steps}

:::{danger}
An SSE route must set `referenced=True` and pass a **called** generator —
`EventStream(stream())`, not `EventStream(stream)`. Without `referenced=True`,
browser speculation opens long-lived prefetch streams and `chirp check` flags it
(`sse_speculation`). Passing the uncalled function never starts the stream.
:::

See [[docs/tutorials/view-transitions-oob|View Transitions + OOB]] for the full
real-time pattern.

## Next steps

You now have the fragment loop running. The natural next step is to build the
same loop with a form, tests, and `chirp check` end to end:

- [[docs/get-started/first-fragment-app|First Fragment App]] — the smallest complete app, with a form POST and tests
- [[docs/about/core-concepts/return-values|Return Values]] — every type a handler can return and what it means
- [[docs/build-apps/html-fragments/fragments|Fragments]] — the fragment-rendering deep dive
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — real-time updates after the page loads

:::{related}
:::

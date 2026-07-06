---
title: First Fragment App
description: Build a small htmx-backed Chirp app with Page, Fragment, forms, tests, and chirp check
draft: false
weight: 25
lang: en
type: doc
tags: [getting-started, fragments, htmx, testing]
keywords: [first app, page, fragment, htmx, form, chirp check]
category: onboarding
---

## What You Will Build

Build a tiny notes app — one Python file, one template — that shows Chirp's whole
hypermedia loop. A browser visit gets a full page. An htmx request gets back only
the named [[docs/build-apps/html-fragments/fragments|fragment]] (a template block)
it asked to swap. A form POST returns the updated fragment, not JSON. The
[[docs/about/core-concepts/return-values|return type]] you choose — `Page` vs
`Fragment` — is the only thing that decides which one a request gets.

You have a choice for the starting point:

- Run `chirp new` when you want auth, sessions, CSRF, static files, and tests
  already wired (a batteries-included scaffold).
- Follow this guide when you want the smallest complete example of the fragment
  model, with nothing you didn't type yourself.

## Build And Run

::::{steps}
:::{step} Create the project files

Make the project directory and its template/test folders:

```bash
mkdir notes-app
cd notes-app
mkdir templates tests
```

Create `app.py`. The `/` handler returns `Page`, which auto-negotiates: a browser
gets the full document, an htmx request gets just the `notes_list` block. The POST
handler always returns that block as a `Fragment`.

```python
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from chirp import App, AppConfig, Fragment, Page, Request


@dataclass(frozen=True, slots=True)
class Note:
    id: int
    body: str


app = App(config=AppConfig(template_dir=Path(__file__).parent / "templates"))

_lock = Lock()
_next_id = 3
_notes = [
    Note(1, "Return types carry rendering intent."),
    Note(2, "One template can serve pages and fragments."),
]


def _all_notes() -> list[Note]:
    with _lock:
        return list(_notes)


def _add_note(body: str) -> None:
    global _next_id
    body = body.strip()
    if not body:
        return
    with _lock:
        _notes.append(Note(_next_id, body))
        _next_id += 1


@app.route("/", name="notes")
def notes(request: Request):
    return Page("notes.html", "notes_list", notes=_all_notes())


@app.route("/notes", methods=["POST"], name="notes.add")
async def add_note(request: Request):
    form = await request.form()
    _add_note(form.get("body", ""))
    return Fragment("notes.html", "notes_list", notes=_all_notes())


if __name__ == "__main__":
    app.run()
```

Create `templates/notes.html`. The `notes_list` block is the unit both handlers
render — once inside the full page, once on its own for the swap.

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notes</title>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"></script>
</head>
<body>
  <main>
    <h1>Notes</h1>

    <form hx-post="{{ url_for('notes.add') }}"
          hx-target="#notes-list"
          hx-swap="outerHTML"
          hx-on::after-request="if (event.detail.successful) this.reset()">
      <input name="body" required>
      <button type="submit">Add</button>
    </form>

    {% block notes_list %}
    <ul id="notes-list">
      {% for note in notes %}
      <li>{{ note.body }}</li>
      {% end %}
    </ul>
    {% endblock %}
  </main>
</body>
</html>
```

:::{/step}
:::{step} Run it

Start the dev server:

```bash
python app.py
```

Open `http://127.0.0.1:8000`. The first request renders the full document. When
the form submits, htmx sends `POST /notes` and Chirp returns only the
`notes_list` block — the same block, served as a fragment because the handler
returned `Fragment`.

:::{/step}
::::{/steps}

## Check The Contract

`chirp check` validates that your routes and template blocks actually line up —
it is the static side of Chirp's [[docs/quality/contracts-debugging/categories|contract]]
model. Run it against the import string for your app object:

```bash
chirp check app:app
```

The check should be clean.

:::{warning}
Rename the `notes_list` block but forget to update the matching
`Page("notes.html", "notes_list", ...)` call and `chirp check` reports the
missing block at startup — before a request ever runs — instead of letting htmx
swap an empty or wrong response into the page.
:::

For CI, promote warnings to failures so a broken swap can't merge:

```bash
chirp check app:app --warnings-as-errors
```

## Add A Smoke Test

Install the testing extra if you did not already:

```bash
uv add "bengal-chirp[testing]"
```

Create `tests/test_notes.py`. Chirp's
[[docs/quality/testing/test-client|TestClient]] is an async context manager;
sending the `HX-Request` header makes Chirp treat the call like an htmx request,
so you can assert the page-vs-fragment behavior directly:

```python
from app import app
from chirp.testing import TestClient


async def test_notes_page_and_fragment() -> None:
    async with TestClient(app) as client:
        page = await client.get("/")
        assert page.status == 200
        assert "<html" in page.text
        assert "Return types carry rendering intent." in page.text

        fragment = await client.post(
            "/notes",
            data={"body": "Fragments keep swaps narrow."},
            headers={"HX-Request": "true"},
        )
        assert fragment.status == 200
        assert "<html" not in fragment.text
        assert 'id="notes-list"' in fragment.text
        assert "Fragments keep swaps narrow." in fragment.text
```

These are plain `async def` tests, so they need `pytest-asyncio` with
`asyncio_mode = "auto"` set under `[tool.pytest.ini_options]` in your
`pyproject.toml` — then `pytest` awaits the coroutines with no per-test marker.

Run it:

```bash
pytest
```

## Where To Go Next

- [[docs/about/core-concepts/return-values|Return Values]] explains when to choose `Template`, `Page`, `Fragment`, `OOB`, `Suspense`, `Stream`, and `EventStream`.
- [[docs/build-apps/html-fragments/fragments|Fragments]] covers named block rendering and htmx targeting in more detail.
- [[docs/examples/_index|Examples]] points to larger runnable apps with validation, OOB updates, SSE, and app shells.

:::{related}
:::

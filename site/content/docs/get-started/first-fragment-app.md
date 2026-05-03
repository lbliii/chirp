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

This guide builds a tiny notes app with one Python file and one template. It
shows Chirp's core loop:

1. A normal browser visit gets a full page.
2. An htmx request gets only the named block it asked to swap.
3. A form POST returns the updated fragment, not JSON.
4. `chirp check` validates the route and template wiring before a user sees it.

Use the generated scaffold when you want auth, sessions, CSRF, static files, and
tests already wired. Use this guide when you want the smallest complete example
of Chirp's fragment model.

## Create The Files

```bash
mkdir notes-app
cd notes-app
mkdir templates tests
```

Create `app.py`:

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

Create `templates/notes.html`:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notes</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
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

## Run It

```bash
python app.py
```

Open `http://127.0.0.1:8000`. The first request renders the full document. When
the form submits, htmx sends `POST /notes` and Chirp returns only the
`notes_list` block.

## Check The Contract

```bash
chirp check app:app
```

The check should be clean. If you rename the `notes_list` block but forget to
update `Page("notes.html", "notes_list", ...)`, Chirp reports the missing block
at startup instead of letting htmx swap an empty or wrong response.

For CI, promote warnings to failures:

```bash
chirp check app:app --warnings-as-errors
```

## Add A Smoke Test

Install the testing extra if you did not already:

```bash
uv add "bengal-chirp[testing]"
```

Create `tests/test_notes.py`:

```python
import pytest

from app import app
from chirp.testing import TestClient


@pytest.mark.anyio
async def test_notes_page_and_fragment() -> None:
    async with TestClient(app) as client:
        page = await client.get("/")
        assert page.status_code == 200
        assert "<html" in page.text
        assert "Return types carry rendering intent." in page.text

        fragment = await client.post(
            "/notes",
            data={"body": "Fragments keep swaps narrow."},
            headers={"HX-Request": "true"},
        )
        assert fragment.status_code == 200
        assert "<html" not in fragment.text
        assert 'id="notes-list"' in fragment.text
        assert "Fragments keep swaps narrow." in fragment.text
```

Run it:

```bash
pytest
```

## Where To Go Next

- [[docs/about/return-values|Return Values]] explains when to choose `Template`, `Page`, `Fragment`, `OOB`, `Suspense`, `Stream`, and `EventStream`.
- [[docs/build-apps/html-fragments/fragments|Fragments]] covers named block rendering and htmx targeting in more detail.
- [[docs/examples|Examples]] points to larger runnable apps with validation, OOB updates, SSE, and app shells.

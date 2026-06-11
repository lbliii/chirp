"""No-JS floor — full CRUD that works with JavaScript completely disabled.

This is the progressive-enhancement *floor*: the baseline that must keep working
when htmx never loads (CSP block, flaky CDN, NoScript, a crawler, a screen reader
in a degraded mode). Every mutation is a plain ``<form method="post">``:

- **Create / edit / delete** are POST-to-a-route forms. HTML forms can only
  issue GET and POST, so the no-JS path deliberately uses POST routes (not PUT/
  DELETE/PATCH) — htmx is *not* required to reach them.
- **Mutations** return a :class:`MutationResult`. A plain (non-htmx) POST gets a
  ``303 See Other`` redirect back to the list — the classic POST/redirect/GET
  pattern that prevents duplicate submits on refresh. An htmx POST gets rendered
  ``Fragment`` swaps instead (the enhanced path) without changing the handler.
- **Validation** returns :class:`ValidationError`, which renders the form block
  with ``422`` and the inline errors regardless of htmx — so a no-JS browser
  shows the re-rendered form with the error message right where the field is.

Run:
    python app.py
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, MutationResult, Page, Request, ValidationError
from chirp.validation import max_length, min_length, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)

# ---------------------------------------------------------------------------
# Data model — frozen for free-threading safety
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Note:
    id: int
    title: str
    body: str


# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_notes: list[Note] = []
_lock = threading.Lock()
_next_id = 1

_SEED = [
    ("Buy milk", "Two percent, not whole."),
    ("Ship the floor demo", "Prove CRUD works with JS disabled."),
]


def _seed() -> None:
    global _next_id
    with _lock:
        for title, body in _SEED:
            _notes.append(Note(id=_next_id, title=title, body=body))
            _next_id += 1


_seed()


def _get_notes() -> list[Note]:
    with _lock:
        return list(_notes)


def _add_note(title: str, body: str) -> Note:
    global _next_id
    with _lock:
        note = Note(id=_next_id, title=title, body=body)
        _next_id += 1
        _notes.append(note)
        return note


def _update_note(note_id: int, title: str, body: str) -> Note | None:
    with _lock:
        for i, note in enumerate(_notes):
            if note.id == note_id:
                updated = Note(id=note.id, title=title, body=body)
                _notes[i] = updated
                return updated
        return None


def _delete_note(note_id: int) -> bool:
    with _lock:
        before = len(_notes)
        _notes[:] = [n for n in _notes if n.id != note_id]
        return len(_notes) < before


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_NOTE_RULES = {
    "title": [required, min_length(3), max_length(100)],
    "body": [max_length(500)],
}

# ---------------------------------------------------------------------------
# Routes — every mutation is reachable with plain GET/POST (no JS required)
# ---------------------------------------------------------------------------


@app.route("/", name="index")
def index():
    """Full page (browser) or fragment (htmx) — the server-rendered list + form."""
    notes = _get_notes()
    return Page(
        "page.html",
        "note_list",
        notes=notes,
        count=len(notes),
        errors={},
        form={},
    )


@app.route("/notes", methods=["POST"], name="notes.add")
async def add_note(request: Request):
    """Create a note.

    Invalid -> 422 + re-rendered create form (ValidationError). Valid -> htmx
    gets fragments, plain POST gets a 303 redirect back to the list.
    """
    form = await request.form()
    result = validate(form, _NOTE_RULES)
    if not result:
        return ValidationError(
            "page.html",
            "create_form",
            errors=result.errors,
            form={"title": form.get("title", ""), "body": form.get("body", "")},
        )

    _add_note(form.get("title", "").strip(), form.get("body", "").strip())
    notes = _get_notes()
    return MutationResult(
        "/",
        Fragment("page.html", "note_list", notes=notes, count=len(notes), errors={}, form={}),
        Fragment("page.html", "note_count", target="note-count", count=len(notes)),
        trigger="noteAdded",
    )


@app.route("/notes/{note_id}/edit", methods=["POST"], name="notes.edit")
async def edit_note(request: Request, note_id: int):
    """Update a note.

    Invalid -> 422 + re-rendered edit form. Valid -> htmx gets fragments, plain
    POST gets a 303 redirect back to the list.
    """
    form = await request.form()
    result = validate(form, _NOTE_RULES)
    if not result:
        return ValidationError(
            "page.html",
            "edit_form",
            errors=result.errors,
            note=Note(
                id=note_id,
                title=form.get("title", ""),
                body=form.get("body", ""),
            ),
        )

    updated = _update_note(note_id, form.get("title", "").strip(), form.get("body", "").strip())
    if updated is None:
        return ("Note not found", 404)

    notes = _get_notes()
    return MutationResult(
        "/",
        Fragment("page.html", "note_list", notes=notes, count=len(notes), errors={}, form={}),
        trigger="noteSaved",
    )


@app.route("/notes/{note_id}/delete", methods=["POST"], name="notes.delete")
def delete_note(note_id: int):
    """Delete a note. htmx gets the updated list; plain POST gets a 303 redirect."""
    _delete_note(note_id)
    notes = _get_notes()
    return MutationResult(
        "/",
        Fragment("page.html", "note_list", notes=notes, count=len(notes), errors={}, form={}),
        Fragment("page.html", "note_count", target="note-count", count=len(notes)),
        trigger="noteDeleted",
    )


if __name__ == "__main__":
    app.run()

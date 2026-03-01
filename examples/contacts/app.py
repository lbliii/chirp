"""Contacts — htmx CRUD with validation, OOB swaps, and response headers.

The canonical htmx demo pattern built with chirp. Exercises every htmx
ergonomic feature: ValidationError for 422 form errors, OOB for
multi-fragment updates, and chainable HX-* response headers.

Run:
    python app.py
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from chirp import OOB, App, AppConfig, Fragment, Page, Request, ValidationError
from chirp.validation import email as email_rule, max_length, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Data model — frozen for free-threading safety
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Contact:
    id: int
    name: str
    email: str


# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_contacts: list[Contact] = []
_lock = threading.Lock()
_next_id = 1

# Seed data so the first page load has content
_SEED = [
    ("Alice Johnson", "alice@example.com"),
    ("Bob Smith", "bob@example.com"),
    ("Carol Williams", "carol@example.com"),
]


def _seed() -> None:
    global _next_id
    with _lock:
        for name, email in _SEED:
            _contacts.append(Contact(id=_next_id, name=name, email=email))
            _next_id += 1


_seed()


def _get_contacts() -> list[Contact]:
    with _lock:
        return list(_contacts)


def _get_contact(contact_id: int) -> Contact | None:
    with _lock:
        for c in _contacts:
            if c.id == contact_id:
                return c
        return None


def _add_contact(name: str, email: str) -> Contact:
    global _next_id
    with _lock:
        contact = Contact(id=_next_id, name=name, email=email)
        _next_id += 1
        _contacts.append(contact)
        return contact


def _update_contact(contact_id: int, name: str, email: str) -> Contact | None:
    with _lock:
        for i, c in enumerate(_contacts):
            if c.id == contact_id:
                updated = Contact(id=c.id, name=name, email=email)
                _contacts[i] = updated
                return updated
        return None


def _delete_contact(contact_id: int) -> bool:
    with _lock:
        before = len(_contacts)
        _contacts[:] = [c for c in _contacts if c.id != contact_id]
        return len(_contacts) < before


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_CONTACT_RULES = {
    "name": [required, max_length(100)],
    "email": [required, email_rule],
}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index(request: Request):
    """Full page or fragment depending on htmx request."""
    contacts = _get_contacts()
    return Page(
        "contacts.html", "contact_table", contacts=contacts, count=len(contacts)
    )


@app.route("/contacts", methods=["POST"])
async def add_contact(request: Request):
    """Add a contact — returns OOB (table + count) or ValidationError."""
    form = await request.form()
    result = validate(form, _CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts.html",
            "contact_form",
            retarget="#form-section",
            errors=result.errors,
            form={"name": form.get("name", ""), "email": form.get("email", "")},
        )

    name = form.get("name", "")
    contact_email = form.get("email", "")
    _add_contact(name, contact_email)
    contacts = _get_contacts()
    return OOB(
        Fragment("contacts.html", "contact_table", contacts=contacts),
        Fragment(
            "contacts.html",
            "contact_count",
            target="contact-count",
            count=len(contacts),
        ),
    )


@app.route("/contacts/search")
def search(request: Request):
    """Search contacts by name — returns the table fragment."""
    q = (request.query.get("q") or "").strip().lower()
    contacts = _get_contacts()
    if q:
        contacts = [c for c in contacts if q in c.name.lower() or q in c.email.lower()]
    return Fragment("contacts.html", "contact_table", contacts=contacts)


@app.route("/contacts/{contact_id}/edit")
def edit_contact(contact_id: int):
    """Return the inline edit form for a contact row."""
    contact = _get_contact(contact_id)
    if contact is None:
        return ("Contact not found", 404)
    return (
        Fragment("contacts.html", "edit_row", contact=contact),
        200,
        {"HX-Push-Url": f"/contacts/{contact_id}/edit"},
    )


@app.route("/contacts/{contact_id}", methods=["PUT"])
async def save_contact(request: Request, contact_id: int):
    """Save an edited contact — returns OOB (row + count) or ValidationError."""
    form = await request.form()
    result = validate(form, _CONTACT_RULES)
    if not result:
        name = form.get("name", "")
        contact_email = form.get("email", "")
        contact = _get_contact(contact_id)
        return ValidationError(
            "contacts.html",
            "edit_row",
            errors=result.errors,
            contact=contact or Contact(id=contact_id, name=name, email=contact_email),
        )

    name = form.get("name", "")
    contact_email = form.get("email", "")
    updated = _update_contact(contact_id, name, contact_email)
    if updated is None:
        return ("Contact not found", 404)

    contacts = _get_contacts()
    return OOB(
        Fragment("contacts.html", "contact_row", contact=updated),
        Fragment(
            "contacts.html",
            "contact_count",
            target="contact-count",
            count=len(contacts),
        ),
    )


@app.route("/contacts/{contact_id}", methods=["DELETE"])
def delete_contact_route(contact_id: int):
    """Delete a contact — returns updated table with HX-Trigger event."""
    _delete_contact(contact_id)
    contacts = _get_contacts()
    return (
        Fragment("contacts.html", "contact_table", contacts=contacts),
        200,
        {"HX-Trigger": "contactDeleted"},
    )


if __name__ == "__main__":
    app.run()

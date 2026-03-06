"""Shared store and view helpers for the contacts shell example."""

import threading
from dataclasses import dataclass

from chirp.validation import email as email_rule
from chirp.validation import max_length, required

_SEED_CONTACTS = (
    ("Alice Johnson", "alice@example.com"),
    ("Bob Smith", "bob@example.com"),
    ("Carol Williams", "carol@example.com"),
)

CONTACT_RULES = {
    "name": [required, max_length(100)],
    "email": [required, email_rule],
}


@dataclass(frozen=True, slots=True)
class Contact:
    id: int
    name: str
    email: str


class ContactStore:
    def __init__(self) -> None:
        self._contacts: list[Contact] = []
        self._lock = threading.Lock()
        self._next_id = 1
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._contacts.clear()
            self._next_id = 1
            for name, email in _SEED_CONTACTS:
                self._contacts.append(Contact(id=self._next_id, name=name, email=email))
                self._next_id += 1

    def all(self) -> list[Contact]:
        with self._lock:
            return list(self._contacts)

    def get(self, contact_id: int) -> Contact | None:
        with self._lock:
            for contact in self._contacts:
                if contact.id == contact_id:
                    return contact
        return None

    def add(self, name: str, email: str) -> Contact:
        with self._lock:
            contact = Contact(id=self._next_id, name=name, email=email)
            self._next_id += 1
            self._contacts.append(contact)
            return contact

    def update(self, contact_id: int, name: str, email: str) -> Contact | None:
        with self._lock:
            for index, contact in enumerate(self._contacts):
                if contact.id == contact_id:
                    updated = Contact(id=contact.id, name=name, email=email)
                    self._contacts[index] = updated
                    return updated
        return None

    def delete(self, contact_id: int) -> bool:
        with self._lock:
            before = len(self._contacts)
            self._contacts[:] = [contact for contact in self._contacts if contact.id != contact_id]
            return len(self._contacts) < before


store = ContactStore()


def reset_store() -> None:
    store.reset()


def normalize_query(value: object | None) -> str:
    return str(value or "").strip()


def filter_contacts(query: str) -> list[Contact]:
    normalized = query.casefold()
    contacts = store.all()
    if not normalized:
        return contacts
    return [
        contact
        for contact in contacts
        if normalized in contact.name.casefold() or normalized in contact.email.casefold()
    ]


def page_context(
    query: str,
    *,
    add_form: dict[str, str] | None = None,
    add_errors: dict[str, list[str]] | None = None,
    editing_contact_id: int | None = None,
    edit_form: dict[str, str] | None = None,
    edit_errors: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    contacts = filter_contacts(query)
    total_count = len(store.all())
    return {
        "query": query,
        "contacts": contacts,
        "visible_count": len(contacts),
        "total_count": total_count,
        "add_form": add_form or {},
        "add_errors": add_errors or {},
        "editing_contact_id": editing_contact_id,
        "edit_form": edit_form or {},
        "edit_errors": edit_errors or {},
    }

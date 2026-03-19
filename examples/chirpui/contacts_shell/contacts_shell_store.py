"""Shared store and view helpers for the contacts shell example."""

import threading
from dataclasses import dataclass

from chirp.validation import email as email_rule
from chirp.validation import max_length, required

GROUPS = ("Engineering", "Design", "Marketing", "Leadership")

GROUP_BADGE_VARIANTS: dict[str, str] = {
    "Engineering": "info",
    "Design": "success",
    "Marketing": "warning",
    "Leadership": "primary",
}

_SEED_CONTACTS = (
    ("Alice Chen", "alice@example.com", "Engineering", "Senior Backend Engineer", "555-0101"),
    ("Bob Martinez", "bob@example.com", "Engineering", "Frontend Developer", "555-0102"),
    ("Carol Williams", "carol@example.com", "Design", "UX Designer", "555-0201"),
    ("David Kim", "david@example.com", "Marketing", "Content Strategist", "555-0301"),
    ("Emma Davis", "emma@example.com", "Leadership", "VP of Engineering", "555-0401"),
    ("Frank Zhao", "frank@example.com", "Engineering", "DevOps Engineer", "555-0103"),
    ("Grace Patel", "grace@example.com", "Design", "Product Designer", "555-0202"),
    ("Henry Okafor", "henry@example.com", "Marketing", "Growth Lead", "555-0302"),
    ("Iris Tanaka", "iris@example.com", "Leadership", "CTO", "555-0402"),
    ("James Lee", "james@example.com", "Engineering", "Staff Engineer", "555-0104"),
    ("Karen Fischer", "karen@example.com", "Design", "Design Lead", "555-0203"),
    ("Liam O'Brien", "liam@example.com", "Marketing", "Marketing Manager", "555-0303"),
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
    group: str = "Engineering"
    role: str = ""
    phone: str = ""


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
            for name, email, group, role, phone in _SEED_CONTACTS:
                self._contacts.append(
                    Contact(
                        id=self._next_id,
                        name=name,
                        email=email,
                        group=group,
                        role=role,
                        phone=phone,
                    )
                )
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

    def add(
        self, name: str, email: str, group: str = "Engineering", role: str = "", phone: str = ""
    ) -> Contact:
        with self._lock:
            contact = Contact(
                id=self._next_id, name=name, email=email, group=group, role=role, phone=phone
            )
            self._next_id += 1
            self._contacts.append(contact)
            return contact

    def update(self, contact_id: int, **fields: str) -> Contact | None:
        with self._lock:
            for index, contact in enumerate(self._contacts):
                if contact.id == contact_id:
                    data = {
                        "id": contact.id,
                        "name": fields.get("name", contact.name),
                        "email": fields.get("email", contact.email),
                        "group": fields.get("group", contact.group),
                        "role": fields.get("role", contact.role),
                        "phone": fields.get("phone", contact.phone),
                    }
                    updated = Contact(**data)
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


def filter_contacts(query: str = "", group: str = "") -> list[Contact]:
    contacts = store.all()
    if group:
        contacts = [c for c in contacts if c.group == group]
    if query:
        normalized = query.casefold()
        contacts = [
            c
            for c in contacts
            if normalized in c.name.casefold()
            or normalized in c.email.casefold()
            or normalized in c.role.casefold()
        ]
    return contacts


def group_counts() -> dict[str, int]:
    contacts = store.all()
    counts: dict[str, int] = {}
    for g in GROUPS:
        counts[g] = sum(1 for c in contacts if c.group == g)
    return counts


def page_context(
    query: str = "",
    group: str = "",
    *,
    add_form: dict[str, str] | None = None,
    add_errors: dict[str, list[str]] | None = None,
    editing_contact_id: int | None = None,
    edit_form: dict[str, str] | None = None,
    edit_errors: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    contacts = filter_contacts(query, group)
    all_contacts = store.all()
    return {
        "query": query,
        "active_group": group,
        "contacts": contacts,
        "visible_count": len(contacts),
        "total_count": len(all_contacts),
        "groups": GROUPS,
        "group_options": [{"value": g, "label": g} for g in GROUPS],
        "group_badge_variants": GROUP_BADGE_VARIANTS,
        "group_counts": group_counts(),
        "add_form": add_form or {},
        "add_errors": add_errors or {},
        "editing_contact_id": editing_contact_id,
        "edit_form": edit_form or {},
        "edit_errors": edit_errors or {},
    }

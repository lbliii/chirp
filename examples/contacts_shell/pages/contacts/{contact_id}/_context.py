from chirp import NotFound

from contacts_shell_store import store


def context(contact_id: str) -> dict[str, object]:
    contact = store.get(int(contact_id))
    if contact is None:
        raise NotFound(f"Contact {contact_id!r} not found")
    return {"contact": contact}

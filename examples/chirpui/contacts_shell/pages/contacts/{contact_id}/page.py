from chirp import Page


def get(contact) -> Page:
    return Page.mounted(
        "contacts/{contact_id}/page.html",
        contact=contact,
    )


def post(contact) -> Page:
    """Fallback POST handler — actions in _actions.py handle save/delete via _action field."""
    return get(contact)

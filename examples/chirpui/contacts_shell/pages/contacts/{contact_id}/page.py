from contacts_shell_store import GROUP_BADGE_VARIANTS

from chirp import Page


def get(contact) -> Page:
    return Page(
        "contacts/{contact_id}/page.html",
        "page_content",
        page_block_name="page_root",
        contact=contact,
        group_badge_variants=GROUP_BADGE_VARIANTS,
    )


def post(contact) -> Page:
    """Fallback POST handler — actions in _actions.py handle save/delete via _action field."""
    return get(contact)

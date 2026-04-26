from contacts_shell_store import normalize_query, page_context

from chirp import Page, Request


def get(contact, request: Request) -> Page:
    query = normalize_query(request.query.get("q"))
    group = normalize_query(request.query.get("group"))
    return Page.mounted(
        "contacts/page.html",
        **page_context(query, group, editing_contact_id=contact.id),
    )

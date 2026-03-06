from chirp import Page, Request

from contacts_shell_store import normalize_query, page_context


def get(contact, request: Request) -> Page:
    query = normalize_query(request.query.get("q"))
    return Page(
        "contacts/page.html",
        "page_content",
        page_block_name="page_root",
        **page_context(query, editing_contact_id=contact.id),
    )

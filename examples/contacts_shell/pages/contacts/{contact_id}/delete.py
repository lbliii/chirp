from chirp import Page, Request

from contacts_shell_store import normalize_query, page_context, store


async def delete(contact, request: Request):
    form = await request.form()
    query = normalize_query(form.get("q") or request.query.get("q"))
    store.delete(contact.id)
    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query),
        ),
        200,
        {"HX-Trigger": "contactDeleted"},
    )

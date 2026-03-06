from chirp import Page, Request, ValidationError
from chirp.validation import validate

from contacts_shell_store import CONTACT_RULES, normalize_query, page_context, store


async def post(contact, request: Request):
    form = await request.form()
    query = normalize_query(form.get("q"))
    result = validate(form, CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts/page.html",
            "contacts_page",
            retarget="#contacts-page",
            **page_context(
                query,
                editing_contact_id=contact.id,
                edit_form={"name": form.get("name", ""), "email": form.get("email", "")},
                edit_errors=result.errors,
            ),
        )

    updated = store.update(contact.id, form.get("name", ""), form.get("email", ""))
    if updated is None:
        return ("Contact not found", 404)

    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query),
        ),
        200,
        {"HX-Trigger": "contactSaved"},
    )

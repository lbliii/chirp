from contacts_shell_store import CONTACT_RULES, normalize_query, page_context, store

from chirp import Page, Request, ValidationError
from chirp.validation import validate


async def post(request: Request):
    form = await request.form()
    query = normalize_query(form.get("q"))
    result = validate(form, CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts/page.html",
            "contact_form",
            retarget="#contact-form-card",
            **page_context(
                query,
                add_form={"name": form.get("name", ""), "email": form.get("email", "")},
                add_errors=result.errors,
            ),
        )

    store.add(form.get("name", ""), form.get("email", ""))
    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query),
        ),
        200,
        {"HX-Trigger": "contactCreated"},
    )

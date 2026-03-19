"""Actions for /contacts — dispatched via _action form field on POST."""

from contacts_shell_store import CONTACT_RULES, normalize_query, page_context, store

from chirp import Page, ValidationError
from chirp.pages.actions import action
from chirp.validation import validate


@action("create")
def create_contact(
    name="", email="", group="Engineering", role="", phone="", q="", group_filter=""
):
    query = normalize_query(q)
    gf = normalize_query(group_filter)
    form = {"name": name, "email": email}
    result = validate(form, CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts/page.html",
            "contacts_page",
            retarget="#contacts-page",
            **page_context(
                query,
                gf,
                add_form={"name": name, "email": email},
                add_errors=result.errors,
            ),
        )

    store.add(name=name, email=email, group=group, role=role, phone=phone)
    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query, gf),
        ),
        200,
        {"HX-Trigger": "contactCreated"},
    )

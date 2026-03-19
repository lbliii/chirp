"""Actions for /contacts/{contact_id} — dispatched via _action form field on POST."""

from contacts_shell_store import CONTACT_RULES, normalize_query, page_context, store

from chirp import Page, ValidationError
from chirp.pages.actions import action
from chirp.validation import validate


@action("save")
def save_contact(contact, name="", email="", group="", role="", phone="", q=""):
    query = normalize_query(q)
    group_filter = normalize_query(group)
    form = {"name": name, "email": email}
    result = validate(form, CONTACT_RULES)
    if not result:
        return ValidationError(
            "contacts/page.html",
            "contacts_page",
            retarget="#contacts-page",
            **page_context(
                query,
                group_filter,
                editing_contact_id=contact.id,
                edit_form={
                    "name": name,
                    "email": email,
                    "role": role,
                    "phone": phone,
                },
                edit_errors=result.errors,
            ),
        )

    updated = store.update(
        contact.id,
        name=name,
        email=email,
        group=group or contact.group,
        role=role,
        phone=phone,
    )
    if updated is None:
        return ("Contact not found", 404)

    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query, group_filter),
        ),
        200,
        {"HX-Trigger": "contactSaved"},
    )


@action("delete")
def delete_contact(contact, q="", group=""):
    query = normalize_query(q)
    group_filter = normalize_query(group)
    store.delete(contact.id)
    return (
        Page(
            "contacts/page.html",
            "page_content",
            page_block_name="page_root",
            **page_context(query, group_filter),
        ),
        200,
        {"HX-Trigger": "contactDeleted"},
    )

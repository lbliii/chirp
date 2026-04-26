from contacts_shell_store import normalize_query, page_context

from chirp import Page, Request


def get(request: Request) -> Page:
    query = normalize_query(request.query.get("q"))
    group = normalize_query(request.query.get("group"))
    return Page.mounted(
        "contacts/page.html",
        **page_context(query, group),
    )


async def post(request: Request) -> Page:
    """Fallback POST handler — actions in _actions.py handle create via _action field."""
    form = await request.form()
    query = normalize_query(form.get("q"))
    group = normalize_query(form.get("group") or form.get("group_filter"))
    return Page.mounted(
        "contacts/page.html",
        **page_context(query, group),
    )

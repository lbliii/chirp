from store import get_settings, toggle_setting

from chirp import Page, Request


def get() -> Page:
    return Page("settings/page.html", "page_content", page_block_name="page_root")


async def post(request: Request):
    form = await request.form()
    toggle_setting(form.get("key", ""))
    # Re-fetch fresh data after toggle (viewmodel ran pre-toggle)
    settings = get_settings()
    categories: dict[str, list] = {}
    for s in settings:
        categories.setdefault(s.category, []).append(s)
    return Page(
        "settings/page.html",
        "page_content",
        page_block_name="page_root",
        categories=categories,
        settings=settings,
    )

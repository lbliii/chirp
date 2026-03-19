from store import get_activity

from chirp import Page


def get() -> Page:
    activity = get_activity(20)
    return Page(
        "about/page.html",
        "page_content",
        page_block_name="page_root",
        activity=activity,
    )

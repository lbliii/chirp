from store import get_items

from chirp import Page


def get() -> Page:
    return Page(
        "page.html",
        "page_content",
        page_block_name="page_root",
        items=get_items(),
    )

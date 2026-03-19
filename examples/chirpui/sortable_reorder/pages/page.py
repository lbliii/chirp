from store import get_steps

from chirp import Page


def get() -> Page:
    steps = get_steps()
    return Page(
        "page.html",
        "page_content",
        page_block_name="page_root",
        steps=steps,
    )

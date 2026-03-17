from chirp import Page


def get() -> Page:
    return Page("about/page.html", "page_content", page_block_name="page_root")

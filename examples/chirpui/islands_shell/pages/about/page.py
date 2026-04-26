from chirp import Page


def get() -> Page:
    return Page.mounted("about/page.html")

from chirp import Page


def get() -> Page:
    return Page.mounted("page.html")

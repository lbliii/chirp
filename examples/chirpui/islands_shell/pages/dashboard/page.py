from chirp import Page


def get() -> Page:
    return Page.mounted("dashboard/page.html")

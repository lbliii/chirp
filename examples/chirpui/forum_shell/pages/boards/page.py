from forum_store import store

from chirp import Page


def get():
    return Page.mounted("boards/page.html", boards=store.boards())

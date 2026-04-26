from forum_store import store

from chirp import Page


def get(board_slug: str):
    board = store.board(board_slug)
    return Page.mounted(
        "boards/{board_slug}/page.html",
        board=board,
        threads=store.board_threads(board_slug),
    )

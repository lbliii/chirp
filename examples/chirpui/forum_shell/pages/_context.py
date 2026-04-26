from forum_store import store


def context():
    return {
        "boards": store.boards(),
        "unread_count": store.unread_count(),
    }

"""Root context — default breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Settings Console",
        "breadcrumb_items": [{"label": "Dashboard", "href": "/"}],
    }

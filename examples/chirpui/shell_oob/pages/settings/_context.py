"""Settings context — override breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Settings",
        "breadcrumb_items": [
            {"label": "Home", "href": "/"},
            {"label": "Settings"},
        ],
    }

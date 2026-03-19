"""Activity context — override breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Activity",
        "breadcrumb_items": [
            {"label": "Dashboard", "href": "/"},
            {"label": "Activity"},
        ],
    }

"""About context — breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "How Islands Work",
        "breadcrumb_items": [
            {"label": "Overview", "href": "/"},
            {"label": "How Islands Work"},
        ],
    }

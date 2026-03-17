"""Dashboard context — breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Dashboard",
        "breadcrumb_items": [
            {"label": "Home", "href": "/"},
            {"label": "Dashboard"},
        ],
    }

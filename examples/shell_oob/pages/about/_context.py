"""About context — override breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "About",
        "breadcrumb_items": [
            {"label": "Home", "href": "/"},
            {"label": "About"},
        ],
    }

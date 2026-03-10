"""Root context — default breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Islands Shell",
        "breadcrumb_items": [{"label": "Home", "href": "/"}],
    }

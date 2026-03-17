"""Root context — default breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Shell OOB Demo",
        "breadcrumb_items": [{"label": "Home", "href": "/"}],
    }

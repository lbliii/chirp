"""Watchlist context — breadcrumbs and page title."""


def context() -> dict:
    return {
        "page_title": "Watchlist",
        "breadcrumb_items": [
            {"label": "Overview", "href": "/"},
            {"label": "Watchlist"},
        ],
    }

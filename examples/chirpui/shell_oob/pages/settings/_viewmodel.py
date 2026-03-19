"""Viewmodel for the settings page — provides grouped categories for display."""

from store import get_settings


def viewmodel():
    settings = get_settings()
    categories: dict[str, list] = {}
    for s in settings:
        categories.setdefault(s.category, []).append(s)
    return {"categories": categories, "settings": settings}

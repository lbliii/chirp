"""Viewmodel for the dashboard page — provides computed stats, settings, and activity."""

from store import dashboard_stats, get_activity, get_settings


def viewmodel():
    return {
        "stats": dashboard_stats(),
        "settings": get_settings(),
        "activity": get_activity(5),
    }

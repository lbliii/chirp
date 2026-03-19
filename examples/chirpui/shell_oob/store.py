"""In-memory store for the settings console example."""

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Setting:
    key: str
    label: str
    description: str
    enabled: bool = False
    category: str = "General"


@dataclass
class ActivityEntry:
    message: str
    timestamp: str
    icon: str = "settings"


_SEED_SETTINGS = [
    Setting(
        "dark_mode",
        "Dark Mode",
        "Enable dark theme across the app",
        enabled=True,
        category="Appearance",
    ),
    Setting(
        "notifications",
        "Email Notifications",
        "Receive email alerts for team changes",
        enabled=True,
        category="Notifications",
    ),
    Setting(
        "slack_alerts",
        "Slack Alerts",
        "Post activity to #team-updates channel",
        enabled=False,
        category="Notifications",
    ),
    Setting(
        "two_factor",
        "Two-Factor Auth",
        "Require 2FA for all team members",
        enabled=True,
        category="Security",
    ),
    Setting(
        "audit_log",
        "Audit Logging",
        "Log all admin actions for compliance",
        enabled=True,
        category="Security",
    ),
    Setting(
        "api_access",
        "API Access",
        "Allow external API integrations",
        enabled=False,
        category="Integrations",
    ),
    Setting(
        "auto_backup",
        "Auto Backup",
        "Daily automatic data backups",
        enabled=True,
        category="General",
    ),
    Setting(
        "maintenance",
        "Maintenance Mode",
        "Show maintenance banner to users",
        enabled=False,
        category="General",
    ),
]

_lock = threading.Lock()
_settings: list[Setting] = []
_activity: list[ActivityEntry] = []


def reset() -> None:
    with _lock:
        _settings.clear()
        _settings.extend(
            Setting(s.key, s.label, s.description, s.enabled, s.category) for s in _SEED_SETTINGS
        )
        _activity.clear()
        _activity.append(
            ActivityEntry("System initialized", datetime.now().strftime("%H:%M"), icon="star")
        )


def get_settings() -> list[Setting]:
    with _lock:
        return list(_settings)


def get_setting(key: str) -> Setting | None:
    with _lock:
        for s in _settings:
            if s.key == key:
                return s
    return None


def toggle_setting(key: str) -> Setting | None:
    with _lock:
        for s in _settings:
            if s.key == key:
                s.enabled = not s.enabled
                action = "enabled" if s.enabled else "disabled"
                _activity.insert(
                    0,
                    ActivityEntry(
                        f"{s.label} {action}",
                        datetime.now().strftime("%H:%M"),
                        icon="check" if s.enabled else "close",
                    ),
                )
                return s
    return None


def get_activity(limit: int = 10) -> list[ActivityEntry]:
    with _lock:
        return list(_activity[:limit])


def dashboard_stats() -> dict[str, object]:
    with _lock:
        total = len(_settings)
        enabled = sum(1 for s in _settings if s.enabled)
        categories = len({s.category for s in _settings})
        return {
            "total_settings": total,
            "enabled_count": enabled,
            "disabled_count": total - enabled,
            "categories": categories,
            "activity_count": len(_activity),
        }


reset()

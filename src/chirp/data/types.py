"""Database-related types and configuration."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection configuration.

    Parsed from a URL string or constructed directly.
    """

    url: str
    pool_size: int = 5
    echo: bool = False
    connect_timeout: float = 30.0
    connect_retries: int = 0


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification received from PostgreSQL LISTEN/NOTIFY.

    Attributes:
        channel: The notification channel name.
        payload: The notification payload string (may be empty).
    """

    channel: str
    payload: str

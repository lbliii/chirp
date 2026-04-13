"""Chirp internationalization (i18n).

Locale detection, message translation, and basic formatting.

Usage::

    app = App(AppConfig(
        i18n_enabled=True,
        i18n_supported_locales=("en", "es", "ja"),
    ))

In templates::

    <h1>{{ t("Welcome to Chirp") }}</h1>
    <p>{{ t("Hello, {name}!", name=user.name) }}</p>

In handlers::

    from chirp.i18n import get_locale, t
    locale = get_locale()  # "es"
    message = t("Hello, {name}!", name="Alice")
"""

import logging

from chirp.i18n.catalog import MessageCatalog
from chirp.i18n.middleware import _locale_var

__all__ = ["MessageCatalog", "get_catalog", "get_locale", "init_catalog", "set_locale", "t"]

logger = logging.getLogger("chirp.i18n")

# Global catalog instance, set during app startup
_catalog: MessageCatalog | None = None


def init_catalog(directory: str = "locales") -> MessageCatalog:
    """Initialize the global message catalog."""
    global _catalog
    _catalog = MessageCatalog(directory)
    return _catalog


def get_catalog() -> MessageCatalog | None:
    """Return the global message catalog."""
    return _catalog


def get_locale() -> str:
    """Return the current request locale.

    Returns "en" if no locale has been set (outside request context).
    """
    try:
        return _locale_var.get()
    except LookupError:
        return "en"


def set_locale(locale: str) -> None:
    """Set the locale for the current context."""
    _locale_var.set(locale)


def t(key: str, **kwargs) -> str:
    """Translate a key using the current locale.

    Template global: ``{{ t("Hello, {name}!", name=user.name) }}``

    Returns the key itself if no catalog is configured or key is missing.
    """
    if _catalog is None:
        if kwargs:
            try:
                return key.format_map(kwargs)
            except KeyError, IndexError:
                return key
        return key
    locale = get_locale()
    return _catalog.translate(locale, key, **kwargs)

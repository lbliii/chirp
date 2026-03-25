"""Message catalog — load JSON translation files.

Simple key-value translations from JSON files. Lazy-loaded per locale.
Missing key returns the source string with a warning (never breaks rendering).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("chirp.i18n")


class MessageCatalog:
    """Manages translation catalogs from JSON files.

    Usage::

        catalog = MessageCatalog("locales")
        catalog.load("es")
        msg = catalog.translate("es", "Hello, {name}!", name="Alice")
    """

    __slots__ = ("_catalogs", "_directories")

    def __init__(self, directory: str | Path = "locales") -> None:
        self._directories: list[Path] = [Path(directory)]
        self._catalogs: dict[str, dict[str, str]] = {}

    def add_directory(self, directory: str | Path) -> None:
        """Add an additional locale directory (e.g., from a plugin)."""
        self._directories.append(Path(directory))

    def load(self, locale: str) -> dict[str, str]:
        """Load translations for a locale. Lazy — loads on first access."""
        if locale in self._catalogs:
            return self._catalogs[locale]

        translations: dict[str, str] = {}
        for directory in self._directories:
            path = directory / f"{locale}.json"
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        translations.update(data)
                except json.JSONDecodeError, OSError:
                    logger.warning("Failed to load locale file: %s", path)

        self._catalogs[locale] = translations
        return translations

    def translate(self, locale: str, key: str, **kwargs) -> str:
        """Look up a translation, with optional interpolation.

        Missing keys return the key itself (never breaks rendering).
        """
        catalog = self.load(locale)
        msg = catalog.get(key, key)
        if msg == key and catalog:
            logger.debug("Missing translation for locale=%s key=%r", locale, key)
        if kwargs:
            try:
                return msg.format_map(kwargs)
            except KeyError, IndexError:
                logger.warning("Translation interpolation failed: %r %r", msg, kwargs)
                return msg
        return msg

    def clear(self) -> None:
        """Clear all cached catalogs."""
        self._catalogs.clear()

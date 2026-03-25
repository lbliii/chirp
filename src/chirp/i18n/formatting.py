"""Locale-aware number and date formatting.

Minimal formatting utilities. For full ICU support, use the ``babel`` library.
"""

import datetime


def format_number(value: int | float, locale: str = "en") -> str:
    """Basic number formatting with locale-appropriate separators."""
    if locale in ("de", "fr", "es", "it", "pt"):
        # European: 1.234,56
        if isinstance(value, float):
            integer_part, decimal_part = f"{value:.2f}".split(".")
            formatted = _add_separator(integer_part, ".")
            return f"{formatted},{decimal_part}"
        return _add_separator(str(value), ".")
    # English-style: 1,234.56
    if isinstance(value, float):
        integer_part, decimal_part = f"{value:.2f}".split(".")
        formatted = _add_separator(integer_part, ",")
        return f"{formatted}.{decimal_part}"
    return _add_separator(str(value), ",")


def _add_separator(s: str, sep: str) -> str:
    """Add thousands separator to a string of digits."""
    negative = s.startswith("-")
    if negative:
        s = s[1:]
    result = []
    for i, digit in enumerate(reversed(s)):
        if i > 0 and i % 3 == 0:
            result.append(sep)
        result.append(digit)
    formatted = "".join(reversed(result))
    return f"-{formatted}" if negative else formatted


def format_date(
    value: datetime.date | datetime.datetime,
    locale: str = "en",
    fmt: str = "short",
) -> str:
    """Basic date formatting.

    Formats:
    - short: 2024-03-15
    - medium: Mar 15, 2024
    - long: March 15, 2024
    """
    if fmt == "short":
        return value.strftime("%Y-%m-%d")
    elif fmt == "medium":
        return value.strftime("%b %d, %Y")
    elif fmt == "long":
        return value.strftime("%B %d, %Y")
    return value.strftime("%Y-%m-%d")

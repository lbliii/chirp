"""Built-in validation rules for chirp forms.

Each validator is a callable with the signature::

    def rule(value: str) -> str | None:
        '''Return error message, or None if valid.'''

Parameterized validators are factory functions that return a validator::

    def max_length(n: int) -> Callable[[str], str | None]:
        def check(value: str) -> str | None:
            if len(value) > n:
                return f"Must be at most {n} characters"
            return None
        return check

Custom validators follow the same protocol — any callable matching
``(str) -> str | None`` works with ``validate()``.
"""

import re
from collections.abc import Callable

# Type alias for a validator function
type Validator = Callable[[str], str | None]


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


def required(value: str) -> str | None:
    """Field must be present and non-empty."""
    if not value or not value.strip():
        return "This field is required"
    return None


# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------


def max_length(n: int) -> Validator:
    """String must be at most *n* characters."""

    def check(value: str) -> str | None:
        if len(value) > n:
            return f"Must be at most {n} characters"
        return None

    return check


def min_length(n: int) -> Validator:
    """String must be at least *n* characters."""

    def check(value: str) -> str | None:
        if len(value) < n:
            return f"Must be at least {n} characters"
        return None

    return check


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------

# Basic email pattern — checks structure, not deliverability
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def email(value: str) -> str | None:
    """Value must be a valid email address (basic format check)."""
    if not _EMAIL_RE.match(value):
        return "Must be a valid email address"
    return None


# Basic URL pattern — checks scheme + host structure
_URL_RE = re.compile(r"^https?://[^\s/$.?#].\S*$", re.IGNORECASE)


def url(value: str) -> str | None:
    """Value must be a valid URL (http/https)."""
    if not _URL_RE.match(value):
        return "Must be a valid URL"
    return None


def matches(pattern: str, message: str | None = None) -> Validator:
    """Value must match the given regex pattern."""
    compiled = re.compile(pattern)

    def check(value: str) -> str | None:
        if not compiled.match(value):
            return message or f"Must match pattern: {pattern}"
        return None

    return check


# ---------------------------------------------------------------------------
# Choice
# ---------------------------------------------------------------------------


def one_of(*choices: str) -> Validator:
    """Value must be one of the given choices."""
    allowed = frozenset(choices)

    def check(value: str) -> str | None:
        if value not in allowed:
            options = ", ".join(sorted(allowed))
            return f"Must be one of: {options}"
        return None

    return check


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def integer(value: str) -> str | None:
    """Value must be a valid integer."""
    try:
        int(value)
    except ValueError, TypeError:
        return "Must be a whole number"
    return None


def number(value: str) -> str | None:
    """Value must be a valid number (int or float)."""
    try:
        float(value)
    except ValueError, TypeError:
        return "Must be a number"
    return None

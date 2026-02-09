"""Built-in chirp template filters.

These are web-framework-specific filters auto-registered on every chirp
kida Environment. They complement Kida's built-in filters with patterns
common in server-rendered HTML + htmx apps.
"""

from typing import Any
from urllib.parse import quote, urlencode


def field_errors(errors: Any, field_name: str) -> list[str]:
    """Extract validation errors for a single form field.

    Safely navigates a ``{field: [messages]}`` dict, returning an
    empty list when *errors* is None, missing, or the field has no
    errors.

    Example:
        {% for msg in errors | field_errors("username") %}
          <span class="error">{{ msg }}</span>
        {% end %}

    """
    if errors is None:
        return []
    if isinstance(errors, dict):
        val = errors.get(field_name, [])
        return list(val) if val else []
    return []


def qs(base: str, **params: Any) -> str:
    """Append query-string parameters to a URL path.

    Omits parameters whose values are falsy (None, "", 0, False)
    so callers can pass optional filters without manual guards.

    Example:
        {{ "/" | qs(page=page + 1, q=search, type=current_type) }}
        → "/?page=3&q=pika"   (when current_type is "")

    """
    filtered = {k: v for k, v in params.items() if v}
    if not filtered:
        return base
    encoded = urlencode(
        {k: str(v) for k, v in filtered.items()},
        quote_via=quote,
    )
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{encoded}"


# All built-in chirp filters, registered automatically on every env.
BUILTIN_FILTERS: dict[str, Any] = {
    "field_errors": field_errors,
    "qs": qs,
}

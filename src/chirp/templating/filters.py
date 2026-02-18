"""Built-in chirp template filters.

These are web-framework-specific filters auto-registered on every chirp
kida Environment. They complement Kida's built-in filters with patterns
common in server-rendered HTML + htmx apps.
"""

import html
import time as time_module
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from kida.template import Markup


def bem(block: str, variant: str = "", modifier: str = "", cls: str = "") -> str:
    """Build chirpui BEM class string: chirpui-{block} chirpui-{block}--{variant} etc.

    Example:
        class="{{ "alert" | bem(variant=variant, cls=cls) }}"
        → "chirpui-alert chirpui-alert--success my-class"
    """
    parts = [f"chirpui-{block}"]
    if variant:
        parts.append(f"chirpui-{block}--{variant}")
    if modifier:
        parts.append(f"chirpui-{block}--{modifier}")
    if cls:
        parts.append(cls)
    return " ".join(parts)


def attr(value: Any, name: str) -> str | Markup:
    """Output an HTML attribute when value is truthy, else empty string.

    Shorthand for optional attributes without ``{% if %}`` blocks.

    Example:
        <a href="{{ href }}"{{ class | attr("class") }}>{{ text }}</a>
        → <a href="/foo" class="active">Foo</a>   (when class is "active")
        → <a href="/foo">Foo</a>                  (when class is None or "")

    """
    if not value:
        return ""
    return Markup(f' {name}="{html.escape(str(value))}"')


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


def timeago(unix_ts: int | float) -> str:
    """Convert a unix timestamp to a human-readable relative time.

    Example:
        {{ message.timestamp | timeago }}  → "3 hours ago"

    """
    if not unix_ts:
        return ""
    delta = int(time_module.time() - unix_ts)
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = delta // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta < 86400:
        h = delta // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = delta // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Pluralize a word based on count.

    Example:
        {{ comments | length | pluralize("comment") }}  → "5 comments"

    """
    if plural is None:
        plural = singular + "s"
    word = singular if count == 1 else plural
    return f"{count} {word}"


def format_time(unix_ts: float) -> str:
    """Format a unix timestamp as ``HH:MM:SS`` (UTC).

    Example:
        {{ msg.created_at | format_time }}  → "14:32:07"

    """
    return datetime.fromtimestamp(unix_ts, UTC).strftime("%H:%M:%S")


def url(value: str, fallback: str = "#") -> str:
    """Safelist URL for href attributes. Uses Kida's url_is_safe.

    Returns the URL if the scheme is safe (http, https, relative), otherwise
    returns fallback. Use when building href from user or external data.

    Example:
        <a href="{{ user_link | url }}">Link</a>
        <a href="{{ external_url | url(fallback='/') }}">External</a>

    """
    from kida.utils.html import safe_url

    return safe_url(str(value), fallback=fallback)


# All built-in chirp filters, registered automatically on every env.
BUILTIN_FILTERS: dict[str, Any] = {
    "attr": attr,
    "bem": bem,
    "field_errors": field_errors,
    "format_time": format_time,
    "pluralize": pluralize,
    "qs": qs,
    "timeago": timeago,
    "url": url,
}

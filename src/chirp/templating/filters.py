"""Built-in chirp template filters.

These are web-framework-specific filters auto-registered on every chirp
kida Environment. They complement Kida's built-in filters with patterns
common in server-rendered HTML + htmx apps.
"""

import html
import json
import time as time_module
from collections.abc import Mapping
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


def _serialize_attr_value(value: Any) -> str:
    """Serialize attribute value into a stable string."""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return str(value)


def html_attrs(value: Any) -> str | Markup:
    """Render HTML attributes from mapping or legacy raw string.

    Contract:
    - ``dict`` / ``Mapping``: escaped, deterministic HTML attributes
    - ``str`` / ``Markup``: pass through (legacy compatibility)
    - ``None`` / ``False``: no output

    Mapping values follow HTML attribute semantics:
    - ``True`` renders as a valueless attribute (e.g. ``disabled``)
    - ``False`` / ``None`` are omitted
    - other values are escaped and rendered as ``key="value"``
    """
    if value is None or value is False:
        return ""

    if isinstance(value, Mapping):
        chunks: list[str] = []
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key or raw_value is None or raw_value is False:
                continue
            escaped_key = html.escape(key, quote=True)
            if raw_value is True:
                chunks.append(f" {escaped_key}")
                continue
            serialized = _serialize_attr_value(raw_value)
            chunks.append(f' {escaped_key}="{html.escape(serialized, quote=True)}"')
        return Markup("".join(chunks))

    text = str(value).strip()
    if not text:
        return ""
    if text.startswith(" "):
        return Markup(text)
    return Markup(f" {text}")


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


def island_props(value: Any) -> Markup:
    """Serialize a value for safe use in ``data-island-props``.

    Returns HTML-escaped JSON as Markup so templates can embed props
    without manual escaping:

        <div data-island-props="{{ props | island_props }}"></div>
    """
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return Markup(html.escape(payload, quote=True))


def island_attrs(
    name: str,
    props: Any | None = None,
    *,
    mount_id: str | None = None,
    version: str = "1",
    src: str | None = None,
    cls: str = "",
) -> Markup:
    """Build a safe island mount attribute string.

    Designed for framework-agnostic mount roots:

        <div{{ island_attrs("editor", props=state, mount_id="editor-root") }}>
            ...
        </div>
    """
    attrs: list[str] = [
        f' data-island="{html.escape(name, quote=True)}"',
        f' data-island-version="{html.escape(version, quote=True)}"',
    ]
    if mount_id:
        attrs.append(f' id="{html.escape(mount_id, quote=True)}"')
    if src:
        attrs.append(f' data-island-src="{html.escape(src, quote=True)}"')
    if cls:
        attrs.append(f' class="{html.escape(cls, quote=True)}"')
    if props is not None:
        attrs.append(f' data-island-props="{island_props(props)}"')
    return Markup("".join(attrs))


def primitive_attrs(
    primitive: str,
    props: dict[str, Any] | None = None,
    *,
    mount_id: str | None = None,
    version: str = "1",
    src: str | None = None,
    cls: str = "",
) -> Markup:
    """Build island attributes with primitive metadata conventions."""
    primitive_props = dict(props or {})
    if "primitive" not in primitive_props:
        primitive_props["primitive"] = primitive
    attrs = island_attrs(
        primitive,
        props=primitive_props,
        mount_id=mount_id,
        version=version,
        src=src,
        cls=cls,
    )
    return Markup(f'{attrs} data-island-primitive="{html.escape(primitive, quote=True)}"')


def optimistic_attrs(
    ops: list[dict[str, Any]] | dict[str, Any],
    *,
    region: str | None = None,
    mount_id: str | None = None,
    version: str = "1",
    pending_class: str = "is-optimistic-pending",
    error_class: str = "is-optimistic-error",
    cls: str = "",
) -> Markup:
    """Mount the blessed ``optimistic_apply`` island primitive.

    Sugar over ``primitive_attrs("optimistic_apply", ...)``. Put the htmx
    trigger (``hx-post`` etc.) on the SAME element; this helper only adds the
    optimistic mount metadata. The runtime applies ``ops`` locally and instantly
    from the client's OWN pre-mutation snapshot, lets htmx do the real request,
    swaps the authoritative server fragment on success (last-write-wins), and
    reverts to the snapshot only when no authoritative fragment lands.

        <button hx-post="/like" hx-swap="outerHTML"
                {{ optimistic_attrs([{"op": "toggleClass", "value": "liked"}],
                                    mount_id="like-1") }}>...</button>

    Raises ``TypeError`` for a malformed op (non-object, or a non-string ``op``
    name) and ``ValueError`` for a policy violation (unknown op, missing op
    arguments, or any server-correlation key), so the helper — the authoritative
    enforcement point — can never emit a mount that would grow per-client server
    view state. Validity is decided by the shared
    ``chirp.contracts.rules_islands.validate_optimistic_op``, so the helper and
    the static ``app.check()`` contract never drift.
    """
    from chirp.contracts.rules_islands import validate_optimistic_op

    if isinstance(ops, dict):
        ops = [ops]
    if not isinstance(ops, (list, tuple)) or not ops:
        raise ValueError("optimistic_attrs requires a non-empty list of ops.")

    normalized: list[dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, dict) or not isinstance(op.get("op"), str):
            raise TypeError(f"optimistic_attrs op must be an object with an 'op' name: {op!r}")
        problem = validate_optimistic_op(op)
        if problem:
            raise ValueError(f"optimistic_attrs op {problem}.")
        normalized.append(dict(op))

    props: dict[str, Any] = {"ops": normalized}
    if region is not None:
        props["region"] = region
    props["pendingClass"] = pending_class
    props["errorClass"] = error_class
    return primitive_attrs(
        "optimistic_apply",
        props=props,
        mount_id=mount_id,
        version=version,
        cls=cls,
    )


BUILTIN_GLOBALS: dict[str, Any] = {
    "island_attrs": island_attrs,
    "optimistic_attrs": optimistic_attrs,
    "primitive_attrs": primitive_attrs,
    # Always expose shell_actions so chirp-ui's ``shell_actions is defined``
    # check (kida 0.2.8 strict undefined variables) works even when no route
    # contributes shell actions. Per-request context overrides this None default.
    "shell_actions": None,
}


# All built-in chirp filters, registered automatically on every env.
BUILTIN_FILTERS: dict[str, Any] = {
    "attr": attr,
    "bem": bem,
    "field_errors": field_errors,
    "format_time": format_time,
    "html_attrs": html_attrs,
    "island_props": island_props,
    "pluralize": pluralize,
    "qs": qs,
    "timeago": timeago,
    "url": url,
}

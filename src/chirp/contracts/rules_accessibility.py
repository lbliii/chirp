"""Accessibility contract checks for templates.

Checks:
- ``a11y_interactive``: htmx URL attrs on non-interactive elements
- ``a11y_label``: form fields without associated labels
"""

import re

from .types import ContractIssue, Severity

# ---------------------------------------------------------------------------
# a11y_interactive — htmx on non-interactive elements
# ---------------------------------------------------------------------------

_INTERACTIVE_ELEMENTS = frozenset(
    {"a", "button", "input", "select", "textarea", "form", "details", "summary"}
)
_HX_TAG_PATTERN = re.compile(
    r"<(\w+)\b([^>]*?)\s+(?:hx-(?:get|post|put|patch|delete))\s*=",
    re.IGNORECASE,
)


def check_accessibility(source: str, template_name: str) -> list[ContractIssue]:
    """Warn about htmx URL attrs on non-interactive elements without role/tabindex."""
    issues: list[ContractIssue] = []
    for match in _HX_TAG_PATTERN.finditer(source):
        tag_name = match.group(1).lower()
        if tag_name in _INTERACTIVE_ELEMENTS:
            continue
        preceding_attrs = match.group(2)
        full_tag_end = source.find(">", match.end())
        trailing_attrs = source[match.end() : full_tag_end] if full_tag_end != -1 else ""
        all_attrs = preceding_attrs + " " + trailing_attrs
        has_role = "role=" in all_attrs.lower()
        has_tabindex = "tabindex=" in all_attrs.lower()
        if not has_role and not has_tabindex:
            hx_match = re.search(r"hx-(?:get|post|put|patch|delete)", all_attrs)
            hx_attr = hx_match.group(0) if hx_match else "hx-*"
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="a11y_interactive",
                    message=(
                        f"{hx_attr} on <{tag_name}> — use <button> or <a>, "
                        'or add role="button" tabindex="0" for accessibility.'
                    ),
                    template=template_name,
                )
            )
    return issues


# ---------------------------------------------------------------------------
# a11y_label — form fields without associated labels
# ---------------------------------------------------------------------------

# Matches <input>, <select>, <textarea> opening tags (self-closing or not).
_LABELABLE_ELEMENT = re.compile(
    r"<(input|select|textarea)\b([^>]*)(?:>|/>)",
    re.IGNORECASE,
)
_ID_ATTR = re.compile(r"""\bid=["']([^"']*)["']""", re.IGNORECASE)
_TYPE_ATTR = re.compile(r"""\btype=["']([^"']*)["']""", re.IGNORECASE)
_NAME_ATTR = re.compile(r"""\bname=["']([^"']*)["']""", re.IGNORECASE)
_ARIA_LABEL_ATTR = re.compile(r"\baria-label(?:ledby)?=", re.IGNORECASE)
_LABEL_FOR = re.compile(r"""<label\b[^>]*\bfor=["']([^"']*)["']""", re.IGNORECASE)

# Wrapping labels: <label ...> ... <input|select|textarea ...> ... </label>
_WRAPPING_LABEL = re.compile(
    r"<label\b[^>]*>(?:(?!</label>).)*?<(?:input|select|textarea)\b",
    re.IGNORECASE | re.DOTALL,
)

# Kida expression: {{ ... }}
_KIDA_EXPR = re.compile(r"\{\{.*?\}\}")

# Types that don't need labels.
_EXEMPT_TYPES = frozenset({"hidden", "submit", "button", "image", "reset"})


def _normalize_for_matching(value: str) -> str:
    """Replace Kida expressions with a wildcard sentinel for matching."""
    return _KIDA_EXPR.sub("__KIDA__", value)


def check_label_association(source: str, template_name: str) -> list[ContractIssue]:
    """Warn when form fields lack an associated label.

    Valid associations (any one is sufficient):
    - ``<label for="id">`` matching the element's ``id``
    - The element is wrapped inside a ``<label>`` tag
    - The element has ``aria-label`` or ``aria-labelledby``

    Exempt elements:
    - ``<input type="hidden|submit|button|image|reset">``
    """
    issues: list[ContractIssue] = []

    # Pre-compute: all label-for targets in this template.
    label_for_values = {
        _normalize_for_matching(m.group(1)) for m in _LABEL_FOR.finditer(source)
    }

    # Pre-compute: character positions covered by wrapping labels.
    wrapping_ranges: list[tuple[int, int]] = []
    for m in _WRAPPING_LABEL.finditer(source):
        # Find the closing </label> after this match.
        close_pos = source.find("</label>", m.end())
        if close_pos != -1:
            wrapping_ranges.append((m.start(), close_pos))

    for match in _LABELABLE_ELEMENT.finditer(source):
        tag_name = match.group(1).lower()
        attrs = match.group(2)

        # Check exempt types (input only).
        if tag_name == "input":
            type_match = _TYPE_ATTR.search(attrs)
            if type_match and type_match.group(1).lower() in _EXEMPT_TYPES:
                continue

        # Check aria-label or aria-labelledby.
        if _ARIA_LABEL_ATTR.search(attrs):
            continue

        # Check label-for association.
        id_match = _ID_ATTR.search(attrs)
        if id_match:
            normalized_id = _normalize_for_matching(id_match.group(1))
            if normalized_id in label_for_values:
                continue

        # Check wrapping label.
        pos = match.start()
        if any(start <= pos <= end for start, end in wrapping_ranges):
            continue

        # No association found — emit warning.
        name_match = _NAME_ATTR.search(attrs)
        field_desc = name_match.group(1) if name_match else tag_name
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="a11y_label",
                message=(
                    f"<{tag_name}> '{field_desc}' has no associated label — "
                    "add <label for=\"...\"> or aria-label."
                ),
                template=template_name,
            )
        )

    return issues

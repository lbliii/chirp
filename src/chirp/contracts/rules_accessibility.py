"""Accessibility checks for htmx interactions."""

import re

from .types import ContractIssue, Severity

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
                    category="accessibility",
                    message=(
                        f"{hx_attr} on <{tag_name}> — use <button> or <a>, "
                        'or add role="button" tabindex="0" for accessibility.'
                    ),
                    template=template_name,
                )
            )
    return issues

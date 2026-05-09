"""CSRF-related template checks."""

import re
from typing import Any

from .types import ContractIssue, Severity

_FORM_PATTERN = re.compile(
    r"<form\b(?P<attrs>[^>]*)>(?P<body>.*?)</form>",
    re.IGNORECASE | re.DOTALL,
)
_UNSAFE_METHOD_PATTERN = re.compile(
    r"\bmethod\s*=\s*['\"]?(post|put|patch|delete)['\"]?",
    re.IGNORECASE,
)
_UNSAFE_HTMX_PATTERN = re.compile(r"\bhx-(?:post|put|patch|delete)\s*=", re.IGNORECASE)
_CSRF_MARKERS = ("csrf_field(", "csrf_token(", 'name="_csrf_token"', "name='_csrf_token'")


def _csrf_middleware_active(middleware_list: list[Any]) -> bool:
    return any(type(middleware).__name__ == "CSRFMiddleware" for middleware in middleware_list)


def _is_mutating_form(attrs: str) -> bool:
    return (
        _UNSAFE_METHOD_PATTERN.search(attrs) is not None
        or _UNSAFE_HTMX_PATTERN.search(attrs) is not None
    )


def _has_csrf_marker(form_source: str) -> bool:
    return any(marker in form_source for marker in _CSRF_MARKERS)


def check_csrf_form_tokens(
    template_sources: dict[str, str],
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Warn when CSRFMiddleware is active but a static mutating form lacks a token."""
    if not _csrf_middleware_active(middleware_list):
        return []

    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _FORM_PATTERN.finditer(source):
            attrs = match.group("attrs")
            if not _is_mutating_form(attrs):
                continue
            form_source = match.group(0)
            if _has_csrf_marker(form_source):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="csrf_form",
                    message=(
                        f"Template '{template_name}' has a mutating <form> but no CSRF field. "
                        "Render {{ csrf_field() }} inside the form, include "
                        '<input name="_csrf_token">, or exempt the route in CSRFConfig.'
                    ),
                    template=template_name,
                )
            )
    return issues

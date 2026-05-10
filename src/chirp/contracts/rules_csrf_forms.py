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
_ATTR_PATTERN = re.compile(
    r"""\b(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:(?P<quote>["'])(?P<quoted>.*?)(?P=quote)|(?P<unquoted>[^\s"'=<>`]+))""",
    re.DOTALL,
)


def _csrf_middleware_active(middleware_list: list[Any]) -> bool:
    return any(type(middleware).__name__ == "CSRFMiddleware" for middleware in middleware_list)


def _csrf_middleware_config(middleware_list: list[Any]) -> Any | None:
    for middleware in middleware_list:
        if type(middleware).__name__ == "CSRFMiddleware":
            return getattr(middleware, "_config", None)
    return None


def _configured_field_name(config: Any | None) -> str:
    field_name = getattr(config, "field_name", "_csrf_token")
    return field_name if isinstance(field_name, str) and field_name else "_csrf_token"


def _configured_exempt_paths(config: Any | None) -> frozenset[str]:
    exempt_paths = getattr(config, "exempt_paths", frozenset())
    if not isinstance(exempt_paths, frozenset):
        return frozenset()
    return exempt_paths


def _attrs_map(attrs: str) -> dict[str, str]:
    attrs_by_name: dict[str, str] = {}
    for match in _ATTR_PATTERN.finditer(attrs):
        value = match.group("quoted")
        if value is None:
            value = match.group("unquoted") or ""
        attrs_by_name[match.group("name").lower()] = value.strip()
    return attrs_by_name


def _is_mutating_form(attrs: str) -> bool:
    return (
        _UNSAFE_METHOD_PATTERN.search(attrs) is not None
        or _UNSAFE_HTMX_PATTERN.search(attrs) is not None
    )


def _mutating_form_target(attrs: str) -> str | None:
    attrs_by_name = _attrs_map(attrs)
    for attr in ("hx-post", "hx-put", "hx-patch", "hx-delete"):
        target = attrs_by_name.get(attr)
        if target:
            return target
    method = attrs_by_name.get("method", "get").upper()
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return attrs_by_name.get("action")
    return None


def _is_exempt_target(target: str | None, exempt_paths: frozenset[str]) -> bool:
    if not target or not target.startswith("/") or "{{" in target or "{%" in target:
        return False
    path = target.split("?", 1)[0]
    return path in exempt_paths


def _has_csrf_marker(form_source: str, field_name: str) -> bool:
    if "csrf_field(" in form_source or "csrf_token(" in form_source:
        return True
    field_pattern = re.compile(
        rf"""\bname\s*=\s*(?:(?P<quote>["']){re.escape(field_name)}(?P=quote)|{re.escape(field_name)}(?=\s|>|/))""",
        re.IGNORECASE,
    )
    return field_pattern.search(form_source) is not None


def check_csrf_form_tokens(
    template_sources: dict[str, str],
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Warn when CSRFMiddleware is active but a static mutating form lacks a token."""
    config = _csrf_middleware_config(middleware_list)
    if config is None and not _csrf_middleware_active(middleware_list):
        return []
    field_name = _configured_field_name(config)
    exempt_paths = _configured_exempt_paths(config)

    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _FORM_PATTERN.finditer(source):
            attrs = match.group("attrs")
            if not _is_mutating_form(attrs):
                continue
            if _is_exempt_target(_mutating_form_target(attrs), exempt_paths):
                continue
            form_source = match.group(0)
            if _has_csrf_marker(form_source, field_name):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="csrf_form",
                    message=(
                        f"Template '{template_name}' has a mutating <form> but no CSRF field. "
                        "Render {{ csrf_field() }} inside the form, include "
                        f'<input name="{field_name}">, or exempt the route in CSRFConfig.'
                    ),
                    template=template_name,
                )
            )
    return issues

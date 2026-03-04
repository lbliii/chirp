"""htmx selector/value checks."""

import re

from .template_scan import extract_hx_target_selectors
from .types import ContractIssue, Severity
from .utils import closest_id

_HTMX_EXTENDED_PREFIXES = frozenset({"closest", "find", "next", "previous"})
_HTMX_SPECIAL_TARGETS = frozenset({"this", "body", "window", "document"})
_HX_INDICATOR_PATTERN = re.compile(r'hx-indicator\s*=\s*["\']([^"\']*)["\']')
_HX_BOOST_PATTERN = re.compile(r'hx-boost\s*=\s*["\']([^"\']*)["\']')


def check_hx_target_selectors(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> tuple[list[ContractIssue], int]:
    """Validate #id hx-target selectors against known static ids."""
    issues: list[ContractIssue] = []
    validated = 0
    for template_name, source in template_sources.items():
        selectors = extract_hx_target_selectors(source)
        for selector in selectors:
            first_word = selector.split()[0] if selector else ""
            if first_word.lower() in _HTMX_SPECIAL_TARGETS:
                continue
            if first_word.lower() in _HTMX_EXTENDED_PREFIXES:
                continue
            if selector.startswith("#"):
                if " " in selector:
                    continue
                target_id = selector[1:]
                if not target_id:
                    continue
                validated += 1
                if target_id not in all_ids:
                    suggestion = closest_id(target_id, all_ids)
                    hint = f' Did you mean "#{suggestion}"?' if suggestion else ""
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="hx-target",
                            message=(
                                f'hx-target="#{target_id}" — no element with '
                                f'id="{target_id}" found in any template.{hint}'
                            ),
                            template=template_name,
                            details=f"Available IDs: {', '.join(sorted(all_ids)[:10])}"
                            if all_ids
                            else None,
                        )
                    )
    return issues, validated


def check_hx_indicator_selectors(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> list[ContractIssue]:
    """Validate #id hx-indicator selectors."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        for match in _HX_INDICATOR_PATTERN.finditer(source):
            value = match.group(1).strip()
            if not value or "{{" in value or "{%" in value:
                continue
            first_word = value.split()[0] if value else ""
            if first_word.lower() in {"closest", "find", "inherit"}:
                continue
            if "," in value:
                continue
            if value.startswith("#"):
                if " " in value:
                    continue
                target_id = value[1:]
                if not target_id:
                    continue
                if target_id not in all_ids:
                    suggestion = closest_id(target_id, all_ids)
                    hint = f' Did you mean "#{suggestion}"?' if suggestion else ""
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="hx-indicator",
                            message=(
                                f'hx-indicator="#{target_id}" — no element with '
                                f'id="{target_id}" found in any template.{hint}'
                            ),
                            template=template_name,
                        )
                    )
    return issues


def check_hx_boost(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Validate hx-boost values are true/false."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        for match in _HX_BOOST_PATTERN.finditer(source):
            value = match.group(1).strip().lower()
            if "{{" in value or "{%" in value:
                continue
            if value not in ("true", "false"):
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="hx-boost",
                        message=f'hx-boost="{match.group(1)}" — must be "true" or "false".',
                        template=template_name,
                    )
                )
    return issues

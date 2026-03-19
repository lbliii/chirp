"""htmx selector/value checks."""

import re

from .template_scan import extract_hx_target_selectors
from .types import ContractIssue, Severity
from .utils import closest_id

_HTMX_EXTENDED_PREFIXES = frozenset({"closest", "find", "next", "previous"})
_HTMX_SPECIAL_TARGETS = frozenset({"this", "body", "window", "document"})
# ChirpUI fragment_island_with_result creates a div with mutation_result_id; docstring examples
# reference it. Skip warning when target is this known pattern ID in chirpui templates.
_CHIRPUI_PATTERN_IDS = frozenset({"update-result"})
_HX_INDICATOR_PATTERN = re.compile(r'hx-indicator\s*=\s*(["\'])(.*?)\1')
_HX_BOOST_PATTERN = re.compile(r'hx-boost\s*=\s*(["\'])(.*?)\1')
_SELECTOR_ATTR_PATTERNS: dict[str, re.Pattern[str]] = {
    "hx-target": re.compile(r'hx-target\s*=\s*(["\'])(.*?)\1'),
    "hx-indicator": re.compile(r'hx-indicator\s*=\s*(["\'])(.*?)\1'),
    "hx-select": re.compile(r'hx-select\s*=\s*(["\'])(.*?)\1'),
    "hx-select-oob": re.compile(r'hx-select-oob\s*=\s*(["\'])(.*?)\1'),
    "hx-include": re.compile(r'hx-include\s*=\s*(["\'])(.*?)\1'),
    "hx-disabled-elt": re.compile(r'hx-disabled-elt\s*=\s*(["\'])(.*?)\1'),
}
_SELECTOR_COMMAND_PREFIXES = frozenset({"closest", "find", "next", "previous", "inherit"})
_SELECTOR_DIRECT_LEADING = frozenset({">", "+", "~"})


def check_hx_target_selectors(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> tuple[list[ContractIssue], int]:
    """Validate #id hx-target selectors against known static ids."""
    issues: list[ContractIssue] = []
    validated = 0
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
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
                if target_id in _CHIRPUI_PATTERN_IDS and template_name.startswith("chirpui/"):
                    continue
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
            value = match.group(2).strip()
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
            value = match.group(2).strip().lower()
            if "{{" in value or "{%" in value:
                continue
            if value not in ("true", "false"):
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="hx-boost",
                        message=f'hx-boost="{match.group(2)}" — must be "true" or "false".',
                        template=template_name,
                    )
                )
    return issues


def _is_balanced_selector(value: str) -> bool:
    """Best-effort balancing check for () and [] in selector values."""
    stack: list[str] = []
    expected_pairs = {")": "(", "]": "["}
    for char in value:
        if char in "([":
            stack.append(char)
            continue
        if char in ")]":
            if not stack or stack[-1] != expected_pairs[char]:
                return False
            stack.pop()
    return not stack


def _selector_syntax_error(value: str) -> str | None:
    """Return an error message when selector value is clearly invalid."""
    if not value:
        return "selector is empty."
    if value[0] in {'"', "'"} and value[-1:] == value[0]:
        return "selector is wrapped in quotes; pass raw selector text."
    if value.startswith(tuple(_SELECTOR_DIRECT_LEADING)):
        return "selector starts with a combinator and has no subject."
    parts = [part.strip() for part in value.split(",")]
    if any(not part for part in parts):
        return "selector list contains an empty entry."
    if not _is_balanced_selector(value):
        return "selector has unbalanced brackets or parentheses."
    return None


def check_selector_syntax(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Validate static selector-bearing HTMX attribute values."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        for attr_name, pattern in _SELECTOR_ATTR_PATTERNS.items():
            for match in pattern.finditer(source):
                value = match.group(2).strip()
                if not value or "{{" in value or "{%" in value:
                    continue
                first_word = value.split()[0].lower()
                if first_word in _SELECTOR_COMMAND_PREFIXES:
                    continue
                if value.lower() in _HTMX_SPECIAL_TARGETS:
                    continue
                error = _selector_syntax_error(value)
                if error is None:
                    continue
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="selector_syntax",
                        message=f'{attr_name}="{value}" — {error}',
                        template=template_name,
                    )
                )
    return issues

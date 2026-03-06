"""Swap safety checks for broad inherited hx-target scopes."""

import re

from .template_scan import (
    extract_ids_with_disinherit,
    extract_mutation_target_ids,
    extract_static_ids,
)
from .types import ContractIssue, Severity

_TAG_WITH_TARGET_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bhx-target\s*=\s*[\"'](?P<target>#[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_MUTATING_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\b(?:hx-(?:post|put|patch|delete)|action)\s*="
    r"\s*[\"'][^\"']*[\"'][^>]*)>",
    re.IGNORECASE,
)
_FORM_POST_PATTERN = re.compile(r'method\s*=\s*["\']post["\']', re.IGNORECASE)
_SSE_SWAP_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-swap\s*=\s*[\"'][^\"']+[\"'][^>]*)>",
    re.IGNORECASE,
)
_SSE_CONNECT_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-connect\s*=\s*[\"'][^\"']+[\"'][^>]*)>",
    re.IGNORECASE,
)


def collect_broad_targets(template_sources: dict[str, str]) -> set[str]:
    """Collect broad inherited hx-target values."""
    broad_targets: set[str] = set()
    for template_name, source in template_sources.items():
        for match in _TAG_WITH_TARGET_PATTERN.finditer(source):
            tag_name = match.group("tag").lower()
            attrs = match.group("attrs")
            target = match.group("target")
            if "{{" in target or "{%" in target:
                continue
            attrs_lower = attrs.lower()
            has_boost = bool(re.search(r'hx-boost\s*=\s*["\']true["\']', attrs_lower))
            if tag_name in {"body", "main"} or has_boost:
                broad_targets.add(f"{target} ({template_name})")
    return broad_targets


def check_swap_safety(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Warn when mutating swaps may inherit broad container targets."""
    issues: list[ContractIssue] = []
    broad_targets = collect_broad_targets(template_sources)
    if not broad_targets:
        return issues
    targets_text = ", ".join(sorted(broad_targets))

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _MUTATING_TAG_PATTERN.finditer(source):
            attrs = match.group("attrs")
            attrs_lower = attrs.lower()
            if "action=" in attrs_lower:
                full_tag = match.group(0)
                if not _FORM_POST_PATTERN.search(full_tag):
                    continue
            if "hx-target=" in attrs_lower:
                continue
            if re.search(r'hx-swap\s*=\s*["\']none["\']', attrs_lower):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="swap_safety",
                    message=(
                        "Mutating htmx request has no explicit hx-target and may inherit "
                        "a broad container target. This can replace large UI regions with "
                        'partial responses. Consider Action() (204), hx-swap="none", '
                        "or an explicit local hx-target."
                    ),
                    template=template_name,
                    details=f"Inherited broad target(s): {targets_text}",
                )
            )
            break

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        has_disinherit = any(
            "hx-disinherit" in match.group("attrs").lower()
            for match in _SSE_CONNECT_TAG_PATTERN.finditer(source)
        )
        if has_disinherit:
            if broad_targets:
                for match in _SSE_SWAP_TAG_PATTERN.finditer(source):
                    if "hx-target=" in match.group("attrs").lower():
                        continue
                    issues.append(
                        ContractIssue(
                            severity=Severity.INFO,
                            category="swap_safety",
                            message=(
                                'Consider adding hx-target="this" on sse-swap '
                                "elements for robustness when using hx-disinherit."
                            ),
                            template=template_name,
                        )
                    )
                    break
            continue
        for match in _SSE_SWAP_TAG_PATTERN.finditer(source):
            if "hx-target=" in match.group("attrs").lower():
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="swap_safety",
                    message=(
                        "SSE swap element has no explicit hx-target and may inherit "
                        "a broad container target. Streamed fragments can land in the "
                        'wrong region. Set hx-target="this" on the element, or add '
                        'hx-disinherit="hx-target hx-swap" on the sse-connect '
                        "ancestor to isolate all SSE swaps."
                    ),
                    template=template_name,
                    details=f"Inherited broad target(s): {targets_text}",
                )
            )
            break

    all_ids: set[str] = set()
    all_ids_with_disinherit: set[str] = set()
    for source in template_sources.values():
        all_ids.update(extract_static_ids(source))
        all_ids_with_disinherit.update(extract_ids_with_disinherit(source))

    seen_fragment_issues: set[tuple[str, str]] = set()
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        mutation_targets = extract_mutation_target_ids(source)
        for target_id in mutation_targets:
            if target_id not in all_ids or target_id in all_ids_with_disinherit:
                continue
            key = (template_name, target_id)
            if key in seen_fragment_issues:
                continue
            seen_fragment_issues.add(key)
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="fragment_island",
                    message=(
                        f"Mutation target #{target_id} has no hx-disinherit. "
                        "Use fragment_island() or add hx-disinherit to avoid inherited "
                        "hx-select/hx-target breaking local swaps."
                    ),
                    template=template_name,
                    details="See chirpui/fragment_island.html",
                )
            )

    return issues

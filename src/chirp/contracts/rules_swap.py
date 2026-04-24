"""Swap safety checks for broad inherited hx-target scopes."""

import re
from collections.abc import Mapping

from .patterns import METHOD_POST as _FORM_POST_PATTERN
from .patterns import SSE_CONNECT_TAG_BASIC as _SSE_CONNECT_TAG_PATTERN
from .template_scan import (
    extract_ids_with_disinherit,
    extract_mutation_target_ids,
    extract_static_ids,
    resolve_template_reference,
)
from .types import ContractIssue, Severity

_EXTENDS_PATTERN = re.compile(r"""{%-?\s*extends\s*["']([^"']+)["']""", re.IGNORECASE)
_TAG_WITH_TARGET_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bhx-target\s*=\s*[\"'](?P<target>#[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_TAG_WITH_SELECT_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bhx-select\s*=\s*[\"'](?P<select>[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_TAG_WITH_SWAP_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bhx-swap\s*=\s*[\"'](?P<swap>[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_TAG_WITH_ID_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bid\s*=\s*[\"'](?P<id>[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_HX_SELECT_COVERAGE_PATTERN = re.compile(
    r'hx-select\s*=|hx-disinherit\s*=\s*["\'][^"\']*\bhx-select\b',
    re.IGNORECASE,
)
_HX_OWN_SELECT_PATTERN = re.compile(r"hx-select\s*=", re.IGNORECASE)
_HX_DISINHERIT_SELECT_PATTERN = re.compile(
    r'hx-disinherit\s*=\s*["\'][^"\']*\bhx-select\b', re.IGNORECASE
)
_MUTATING_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\b(?:hx-(?:post|put|patch|delete)|action)\s*="
    r"\s*[\"'][^\"']*[\"'][^>]*)>",
    re.IGNORECASE,
)
_SSE_SWAP_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-swap\s*=\s*[\"'][^\"']+[\"'][^>]*)>",
    re.IGNORECASE,
)
_HX_BOOST_TRUE = re.compile(r'hx-boost\s*=\s*["\']true["\']', re.IGNORECASE)
_HX_BOOST_FALSE = re.compile(r'hx-boost\s*=\s*["\']false["\']', re.IGNORECASE)
_HX_SWAP_NONE = re.compile(r'hx-swap\s*=\s*["\']none["\']', re.IGNORECASE)
_TRANSITION_TRUE = re.compile(r"(?:^|\s)transition:true(?:\s|$)", re.IGNORECASE)
_LIVE_UPDATE_MARKERS = re.compile(r"\b(?:hx-swap-oob|sse-connect)\b", re.IGNORECASE)
_INLINE_VIEW_TRANSITION_NAME = re.compile(r"view-transition-name\s*:", re.IGNORECASE)
_STYLE_ID_VIEW_TRANSITION = re.compile(
    r"#(?P<id>[A-Za-z_][\w:-]*)\s*\{[^}]*\bview-transition-name\s*:",
    re.IGNORECASE | re.DOTALL,
)

_BROAD_CONTAINER_TAGS = frozenset(
    {
        "body",
        "main",
        "div",
        "section",
        "article",
        "aside",
        "nav",
        "header",
        "footer",
        "form",
        "details",
        "dialog",
        "fieldset",
        "figure",
        "hgroup",
        "search",
    }
)


def _extends_ancestors(
    start: str,
    template_sources: dict[str, str],
    template_aliases: Mapping[str, str] | None = None,
) -> set[str]:
    """Return all templates reachable upward from *start* via {% extends %} chains."""
    ancestors: set[str] = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in ancestors or name not in template_sources:
            continue
        ancestors.add(name)
        queue.extend(
            resolve_template_reference(m.group(1), name, template_aliases)
            for m in _EXTENDS_PATTERN.finditer(template_sources[name])
        )
    return ancestors


def _collect_broad_selects_map(
    template_sources: dict[str, str],
) -> dict[str, list[str]]:
    """Return {template_name: [select_value, ...]} for broad containers.

    A broad container is a ``<body>``, ``<main>``, or any element with
    ``hx-boost="true"`` that also carries an ``hx-select`` attribute.
    """
    result: dict[str, list[str]] = {}
    for template_name, source in template_sources.items():
        for match in _TAG_WITH_SELECT_PATTERN.finditer(source):
            tag_name = match.group("tag").lower()
            if tag_name not in _BROAD_CONTAINER_TAGS:
                continue
            attrs = match.group("attrs")
            select = match.group("select")
            if "{{" in select or "{%" in select:
                continue
            attrs_lower = attrs.lower()
            has_boost = bool(_HX_BOOST_TRUE.search(attrs_lower))
            if tag_name in {"body", "main"} or has_boost:
                result.setdefault(template_name, []).append(select)
    return result


def collect_broad_selects(template_sources: dict[str, str]) -> set[str]:
    """Collect hx-select values from broad containers (body, main, or hx-boost="true" elements).

    These are potential inheritance sources: any mutating HTMX element nested inside
    such a container will inherit the select, which silently breaks fragment swaps when
    the response doesn't contain the selector target.
    """
    broad_selects: set[str] = set()
    for template_name, selects in _collect_broad_selects_map(template_sources).items():
        for select in selects:
            broad_selects.add(f'"{select}" ({template_name})')
    return broad_selects


def collect_broad_targets(template_sources: dict[str, str]) -> set[str]:
    """Collect broad inherited hx-target values."""
    broad_targets: set[str] = set()
    for template_name, source in template_sources.items():
        for match in _TAG_WITH_TARGET_PATTERN.finditer(source):
            tag_name = match.group("tag").lower()
            if tag_name not in _BROAD_CONTAINER_TAGS:
                continue
            attrs = match.group("attrs")
            target = match.group("target")
            if "{{" in target or "{%" in target:
                continue
            attrs_lower = attrs.lower()
            has_boost = bool(_HX_BOOST_TRUE.search(attrs_lower))
            if tag_name in {"body", "main"} or has_boost:
                broad_targets.add(f"{target} ({template_name})")
    return broad_targets


def _has_live_updates(template_sources: dict[str, str]) -> bool:
    """Return True if any template uses OOB or SSE live-update markers."""
    return any(_LIVE_UPDATE_MARKERS.search(source) for source in template_sources.values())


def _collect_broad_target_ids(template_sources: dict[str, str]) -> set[str]:
    """Collect static broad hx-target IDs without template-name decoration."""
    target_ids: set[str] = set()
    for source in template_sources.values():
        for match in _TAG_WITH_TARGET_PATTERN.finditer(source):
            tag_name = match.group("tag").lower()
            if tag_name not in _BROAD_CONTAINER_TAGS:
                continue
            target = match.group("target")
            if "{{" in target or "{%" in target:
                continue
            attrs_lower = match.group("attrs").lower()
            has_boost = bool(_HX_BOOST_TRUE.search(attrs_lower))
            if tag_name in {"body", "main"} or has_boost:
                target_ids.add(target.removeprefix("#"))
    return target_ids


def check_view_transition_safety(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Warn when View Transitions are scoped to broad live-update containers.

    OOB swaps and SSE fragments update descendants after the page has loaded.
    If a broad content container owns ``transition:true`` or a CSS
    ``view-transition-name``, those child updates can animate the entire content
    region and make the UI appear to disappear.
    """
    if not _has_live_updates(template_sources):
        return []

    issues: list[ContractIssue] = []
    broad_target_ids = _collect_broad_target_ids(template_sources)

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _TAG_WITH_SWAP_PATTERN.finditer(source):
            tag_name = match.group("tag").lower()
            if tag_name not in _BROAD_CONTAINER_TAGS:
                continue
            attrs = match.group("attrs")
            attrs_lower = attrs.lower()
            has_boost = bool(_HX_BOOST_TRUE.search(attrs_lower))
            is_broad = tag_name in {"body", "main"} or has_boost or "hx-target=" in attrs_lower
            if not is_broad or not _TRANSITION_TRUE.search(match.group("swap")):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="view_transition_scope",
                    message=(
                        "Broad htmx container uses transition:true while the app also "
                        "uses OOB/SSE updates. Child live updates can trigger a "
                        "full-region View Transition and make content flicker or "
                        "disappear. Remove transition:true from the container and put "
                        "it on navigation links instead."
                    ),
                    template=template_name,
                )
            )
            break

    if not broad_target_ids:
        return issues

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _STYLE_ID_VIEW_TRANSITION.finditer(source):
            target_id = match.group("id")
            if target_id not in broad_target_ids:
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="view_transition_scope",
                    message=(
                        f"#{target_id} has view-transition-name while the app also "
                        "uses OOB/SSE updates. Scope view-transition-name to an "
                        "element that changes only during navigation, not the broad "
                        "swap container that contains live-update targets."
                    ),
                    template=template_name,
                )
            )
            break

        for match in _TAG_WITH_ID_PATTERN.finditer(source):
            target_id = match.group("id")
            if target_id not in broad_target_ids:
                continue
            attrs = match.group("attrs")
            if not _INLINE_VIEW_TRANSITION_NAME.search(attrs):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="view_transition_scope",
                    message=(
                        f"#{target_id} has inline view-transition-name while the app "
                        "also uses OOB/SSE updates. Scope the transition to "
                        "navigation-only content instead of the broad live-update "
                        "container."
                    ),
                    template=template_name,
                )
            )
            break

    return issues


def check_swap_safety(
    template_sources: dict[str, str],
    *,
    all_ids: set[str] | None = None,
    all_ids_with_disinherit: set[str] | None = None,
    template_aliases: Mapping[str, str] | None = None,
) -> list[ContractIssue]:
    """Warn when mutating swaps may inherit broad container targets or selects."""
    issues: list[ContractIssue] = []

    # Check hx-select inheritance: if a broad container sets hx-select and an app
    # template has a mutating element without explicit hx-select coverage, fragment
    # responses won't contain the select target and HTMX will swap in empty content.
    # Only flag templates whose {% extends %} chain actually reaches a layout with the
    # broad select — templates that extend shell.html (no broad select) are not affected.
    broad_selects_map = _collect_broad_selects_map(template_sources)
    if broad_selects_map:
        for template_name, source in template_sources.items():
            if template_name.startswith(("chirp/", "chirpui/")):
                continue
            # Walk this template's extends chain; collect only the broad selects from
            # layouts that are actually in its inheritance hierarchy.
            ancestors = _extends_ancestors(template_name, template_sources, template_aliases)
            relevant_selects: list[str] = []
            for ancestor, selects in broad_selects_map.items():
                if ancestor in ancestors:
                    relevant_selects.extend(f'"{sel}" ({ancestor})' for sel in selects)
            if not relevant_selects:
                continue
            selects_text = ", ".join(sorted(relevant_selects))
            for match in _MUTATING_TAG_PATTERN.finditer(source):
                attrs = match.group("attrs")
                attrs_lower = attrs.lower()
                if "action=" in attrs_lower:
                    full_tag = match.group(0)
                    if not _FORM_POST_PATTERN.search(full_tag):
                        continue
                if _HX_SELECT_COVERAGE_PATTERN.search(attrs):
                    continue
                if _HX_SWAP_NONE.search(attrs_lower):
                    continue
                if _HX_BOOST_FALSE.search(attrs_lower):
                    continue
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="select_inheritance",
                        message=(
                            "Mutating htmx element has no explicit hx-select and may inherit "
                            "a selector from a broad container. Fragment responses that don't "
                            "include the selector target will swap in empty content silently. "
                            "Use shell.html (no global hx-select) for fragment-only apps, "
                            'or add hx-disinherit="hx-select" on this element.'
                        ),
                        template=template_name,
                        details=f"Inherited broad select(s): {selects_text}",
                    )
                )
                break

    # Second pass: forms with hx-disinherit="hx-select" but no own hx-select= are
    # still vulnerable. hx-disinherit prevents children from inheriting, but the form
    # itself still receives the inherited hx-select from its parent container.
    if broad_selects_map:
        for template_name, source in template_sources.items():
            if template_name.startswith(("chirp/", "chirpui/")):
                continue
            ancestors = _extends_ancestors(template_name, template_sources, template_aliases)
            if not any(a in broad_selects_map for a in ancestors):
                continue
            for match in _MUTATING_TAG_PATTERN.finditer(source):
                attrs = match.group("attrs")
                if not _HX_DISINHERIT_SELECT_PATTERN.search(attrs):
                    continue
                if _HX_OWN_SELECT_PATTERN.search(attrs):
                    continue
                if _HX_SWAP_NONE.search(attrs):
                    continue
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="select_inheritance",
                        message=(
                            'Mutating element has hx-disinherit="hx-select" but no own '
                            "hx-select attribute. hx-disinherit only prevents children from "
                            "inheriting — the element itself still receives the inherited "
                            'hx-select. Add hx-select="unset" on the element to override.'
                        ),
                        template=template_name,
                    )
                )
                break

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
            if _HX_SWAP_NONE.search(attrs_lower):
                continue
            if _HX_BOOST_FALSE.search(attrs_lower):
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

    if all_ids is None:
        all_ids = set()
        for source in template_sources.values():
            all_ids.update(extract_static_ids(source))
    if all_ids_with_disinherit is None:
        all_ids_with_disinherit = set()
        for source in template_sources.values():
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

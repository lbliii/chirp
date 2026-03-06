"""Template source scanners used by contracts checker."""

import re
from typing import Any

# \baction\b avoids matching "action" inside form_action, data-action, etc.
_ACTION_OR_HX = r"(hx-(?:get|post|put|patch|delete)|\baction\b)"
_ATTR_PATTERN_DOUBLE = re.compile(
    rf'{_ACTION_OR_HX}\s*=\s*"([^"]*)"',
)
_ATTR_PATTERN_SINGLE = re.compile(
    rf"{_ACTION_OR_HX}\s*=\s*'([^']*)'",
)
_ATTRS_MAP_PATTERN = re.compile(rf"""["']{_ACTION_OR_HX}["']\s*:\s*["']([^"']*)["'](?=\s*[,}}])""")
_HX_TARGET_PATTERN = re.compile(r'hx-target\s*=\s*["\']([^"\']*)["\']')
_ID_PATTERN = re.compile(r'\bid\s*=\s*["\']([^"\']*)["\']')
_TEMPLATE_REF_PATTERN = re.compile(
    r"""\{%-?\s*(?:extends|include|from|import)\s+["']([^"']+)["']"""
)
_TEMPLATE_SOURCE_SUFFIXES = (".html", ".htm", ".jinja", ".j2")
_FRAGMENT_ISLAND_PATTERN = re.compile(r'fragment_island\s*\(\s*["\']([^"\']+)["\']')
_ID_WITH_DISINHERIT_PATTERN = re.compile(
    r'<[^>]+\bid\s*=\s*["\']([^"\']+)["\'][^>]*hx-disinherit',
    re.IGNORECASE | re.DOTALL,
)
_ID_WITH_DISINHERIT_REVERSE = re.compile(
    r'<[^>]+hx-disinherit[^>]*\bid\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
_MUTATING_WITH_TARGET = re.compile(
    r"<(?:form|button|a|div|span)\b[^>]*\b(?:hx-(?:post|put|patch|delete)|\baction\b)\s*="
    r'[^>]*\bhx-target\s*=\s*["\']#([^"\'\s]+)["\']',
    re.IGNORECASE,
)


def get_form_method(source: str, action_pos: int) -> str | None:
    """Return POST only when form has method='post', otherwise GET."""
    before = source[:action_pos]
    form_matches = list(re.finditer(r"<form\b", before, re.IGNORECASE))
    if not form_matches:
        return None
    form_start = form_matches[-1].start()
    tag_end = source.find(">", form_start)
    if tag_end == -1 or tag_end < action_pos:
        return None
    form_tag = source[form_start:tag_end]
    if re.search(r'method\s*=\s*["\']post["\']', form_tag, re.IGNORECASE):
        return "POST"
    return "GET"


def extract_targets_from_source(source: str) -> list[tuple[str, str, str | None]]:
    """Extract (attr_name, url, method_override) from template source."""
    targets: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()

    def _append_target(attr_name: str, url: str, method_override: str | None) -> None:
        if "{{" in url or "~" in url or "{%" in url or url.startswith(("#", "javascript:")):
            return
        target = (attr_name, url, method_override)
        if target in seen:
            return
        seen.add(target)
        targets.append(target)

    for pattern in (_ATTR_PATTERN_DOUBLE, _ATTR_PATTERN_SINGLE):
        for match in pattern.finditer(source):
            attr_name = match.group(1)
            url = match.group(2)
            method_override = (
                get_form_method(source, match.start()) if attr_name == "action" else None
            )
            _append_target(attr_name, url, method_override)

    for match in _ATTRS_MAP_PATTERN.finditer(source):
        attr_name = match.group(1)
        url = match.group(2)
        _append_target(attr_name, url, None)

    return targets


def extract_hx_target_selectors(source: str) -> list[str]:
    """Extract static hx-target selector values from source."""
    selectors: list[str] = []
    for match in _HX_TARGET_PATTERN.finditer(source):
        value = match.group(1).strip()
        if "{{" in value or "{%" in value:
            continue
        if value:
            selectors.append(value)
    return selectors


def extract_static_ids(source: str) -> set[str]:
    """Extract static id= values from source."""
    ids: set[str] = set()
    for match in _ID_PATTERN.finditer(source):
        value = match.group(1).strip()
        if value and "{{" not in value and "{%" not in value:
            ids.add(value)
    return ids


def extract_template_references(source: str) -> set[str]:
    """Extract static template references from Kida template tags."""
    return {m.group(1) for m in _TEMPLATE_REF_PATTERN.finditer(source)}


def extract_fragment_island_ids(source: str) -> set[str]:
    """Extract id values from fragment_island() macro calls."""
    return {m.group(1) for m in _FRAGMENT_ISLAND_PATTERN.finditer(source)}


def extract_ids_with_disinherit(source: str) -> set[str]:
    """Extract id values from elements that have hx-disinherit."""
    ids: set[str] = set()
    for pattern in (_ID_WITH_DISINHERIT_PATTERN, _ID_WITH_DISINHERIT_REVERSE):
        for m in pattern.finditer(source):
            val = m.group(1).strip()
            if val and "{{" not in val and "{%" not in val:
                ids.add(val)
    ids.update(extract_fragment_island_ids(source))
    return ids


def extract_mutation_target_ids(source: str) -> set[str]:
    """Extract #id values from hx-target when element is mutating."""
    ids: set[str] = set()
    for m in _MUTATING_WITH_TARGET.finditer(source):
        val = m.group(1).strip()
        if val and "{{" not in val and "{%" not in val:
            ids.add(val)
    mutating_blocks = re.findall(
        r"(?:hx-(?:post|put|patch|delete)|hx_post|hx_put|hx_patch|hx_delete|action)\s*[=:][^}]+"
        r'(?:hx-target|hx_target)\s*[=:]\s*["\']#([^"\']+)["\']',
        source,
        re.IGNORECASE | re.DOTALL,
    )
    for val in mutating_blocks:
        if "{{" not in val and "{%" not in val:
            ids.add(val.strip())
    target_in_mutating = re.findall(
        r'(?:hx-target|hx_target)\s*[=:]\s*["\']#([^"\']+)["\'][^}]*'
        r"(?:hx-(?:post|put|patch|delete)|hx_post|hx_put|hx_patch|hx_delete)",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    for val in target_in_mutating:
        if "{{" not in val and "{%" not in val:
            ids.add(val.strip())
    return ids


def load_template_sources(kida_env: Any) -> dict[str, str]:
    """Load all template sources from environment loader."""
    sources: dict[str, str] = {}
    loader = kida_env.loader
    if loader is None:
        return sources
    list_fn = getattr(loader, "list_templates", None)
    if list_fn is None:
        return sources
    try:
        names = list_fn()
        for name in names:
            if not name.endswith(_TEMPLATE_SOURCE_SUFFIXES):
                continue
            try:
                source, _ = loader.get_source(name)
                sources[name] = source
            except Exception:
                pass
    except Exception:
        pass
    return sources

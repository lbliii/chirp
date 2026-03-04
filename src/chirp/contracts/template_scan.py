"""Template source scanners used by contracts checker."""

import re
from typing import Any

_ATTR_PATTERN_DOUBLE = re.compile(
    r'(hx-(?:get|post|put|patch|delete)|action)\s*=\s*"([^"]*)"',
)
_ATTR_PATTERN_SINGLE = re.compile(
    r"(hx-(?:get|post|put|patch|delete)|action)\s*=\s*'([^']*)'",
)
_ATTRS_MAP_PATTERN = re.compile(
    r"""["'](hx-(?:get|post|put|patch|delete)|action)["']\s*:\s*["']([^"']*)["'](?=\s*[,}])"""
)
_HX_TARGET_PATTERN = re.compile(r'hx-target\s*=\s*["\']([^"\']*)["\']')
_ID_PATTERN = re.compile(r'\bid\s*=\s*["\']([^"\']*)["\']')
_TEMPLATE_REF_PATTERN = re.compile(
    r"""\{%-?\s*(?:extends|include|from|import)\s+["']([^"']+)["']"""
)
_TEMPLATE_SOURCE_SUFFIXES = (".html", ".htm", ".jinja", ".j2")


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
            method_override = get_form_method(source, match.start()) if attr_name == "action" else None
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

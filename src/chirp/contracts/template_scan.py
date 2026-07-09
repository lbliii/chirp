"""Template source scanners used by contracts checker."""

import logging
import posixpath
import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal

from .patterns import ID_ATTR as _ID_PATTERN
from .patterns import METHOD_POST

# \baction\b avoids matching "action" inside form_action, data-action, etc.
_ACTION_OR_HX = r"(hx-(?:get|post|put|patch|delete)|hx-sse:connect|sse-connect|\baction\b)"
_ATTR_PATTERN_DOUBLE = re.compile(
    rf'{_ACTION_OR_HX}\s*=\s*"([^"]*)"',
)
_ATTR_PATTERN_SINGLE = re.compile(
    rf"{_ACTION_OR_HX}\s*=\s*'([^']*)'",
)
_ATTRS_MAP_PATTERN = re.compile(rf"""["']{_ACTION_OR_HX}["']\s*:\s*["']([^"']*)["'](?=\s*[,}}])""")
_CONFIRM_URL_PATTERN = re.compile(r'confirm_url\s*=\s*["\']([^"\']*)["\']')
_CONFIRM_METHOD_PATTERN = re.compile(r'confirm_method\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_HX_TARGET_PATTERN = re.compile(r'hx-target\s*=\s*["\']([^"\']*)["\']')
_TEMPLATE_REF_PATTERN = re.compile(
    r"""\{%-?\s*(?:extends|include|from|import)\s+["']([^"']+)["']"""
)
_TEMPLATE_SOURCE_SUFFIXES = (".html", ".htm", ".jinja", ".j2")
_FRAGMENT_ISLAND_PATTERN = re.compile(r'fragment_island\s*\(\s*["\']([^"\']+)["\']')
_WIZARD_FORM_PATTERN = re.compile(r'wizard_form\s*\(\s*["\']([^"\']+)["\']')
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
_LEGACY_ACTION_PATTERN = re.compile(r'(?<![-\w])action\s*=\s*["\']([A-Za-z][A-Za-z0-9_-]*)["\']')
_HREF_ATTR_PATTERN = re.compile(r'href\s*=\s*["\']([^"\']*)["\']')
_MACRO_URL_ARG_PATTERN = re.compile(
    r"""(?:href|url|search_url|action_url)\s*=\s*["'](/[^"']*?)["']"""
)
_POSITIONAL_URL_ARG_PATTERN = re.compile(r"""\(\s*["'](/[a-zA-Z][a-zA-Z0-9_/{}-]*)["']""")
_HTMX_PARTIAL_PATTERN = re.compile(
    r'<htmx-partial\b[^>]*(?<![-\w])src\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_FORM_OPEN_TAG = re.compile(r"<form\b", re.IGNORECASE)
_MUTATING_BLOCK_TARGET = re.compile(
    r"(?:hx-(?:post|put|patch|delete)|hx_post|hx_put|hx_patch|hx_delete|\baction\b)\s*[=:][^}]+"
    r'(?:hx-target|hx_target)\s*[=:]\s*["\']#([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
_TARGET_IN_MUTATING = re.compile(
    r'(?:hx-target|hx_target)\s*[=:]\s*["\']#([^"\']+)["\'][^}]*'
    r"(?:hx-(?:post|put|patch|delete)|hx_post|hx_put|hx_patch|hx_delete)",
    re.IGNORECASE | re.DOTALL,
)
_HTMX_QUERY_PREFIX = re.compile(
    r"\bhtmx\.ajax\(\s*([\"'])QUERY\1\s*,\s*([\"'])(?P<url>/[^\"']*)\2",
    re.IGNORECASE,
)
_FETCH_PREFIX = re.compile(r"\bfetch\(\s*([\"'])(?P<url>/[^\"']*)\1", re.IGNORECASE)
_QUERY_METHOD_OPTION = re.compile(
    r"(?:\bmethod\b|[\"']method[\"'])\s*:\s*([\"'])QUERY\1",
    re.IGNORECASE,
)
_HEADERS_OPTION = re.compile(r"(?:\bheaders\b|[\"']headers[\"'])\s*:", re.IGNORECASE)
_CONTENT_TYPE_OPTION = re.compile(
    r"([\"'])content-type\1\s*:\s*([\"'])(?P<content_type>[^\"']+)\2",
    re.IGNORECASE,
)
_SCRIPT_BLOCK = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_TYPE_ATTR = re.compile(
    r"(?<![-\w])type\s*=\s*(?:[\"'](?P<quoted>[^\"']*)[\"']|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
_SCRIPT_SRC_ATTR = re.compile(r"(?<![-\w])src\s*=", re.IGNORECASE)
_JAVASCRIPT_TYPES = frozenset(
    {
        "application/ecmascript",
        "application/javascript",
        "module",
        "text/ecmascript",
        "text/javascript",
    }
)


@dataclass(frozen=True, slots=True)
class QueryClientReference:
    """One statically knowable programmatic HTTP QUERY client call."""

    client: Literal["fetch", "htmx.ajax"]
    url: str
    content_type: str | None
    content_type_known: bool


def _javascript_call_suffix(source: str, start: int) -> str:
    """Return the remainder of one call, stopping at its balanced ``)``."""
    depth = 1
    quote: str | None = None
    escaped = False
    index = start
    while index < len(source):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[start:index]
        index += 1
    return source[start:]


def _query_client_reference(
    client: Literal["fetch", "htmx.ajax"],
    url: str,
    options: str,
) -> QueryClientReference:
    content_type_match = _CONTENT_TYPE_OPTION.search(options)
    content_type = (
        content_type_match.group("content_type").strip() if content_type_match is not None else None
    )
    return QueryClientReference(
        client=client,
        url=url,
        content_type=content_type,
        content_type_known=content_type is not None or _HEADERS_OPTION.search(options) is None,
    )


def _executable_script_bodies(source: str) -> tuple[str, ...]:
    bodies: list[str] = []
    for match in _SCRIPT_BLOCK.finditer(source):
        attrs = match.group("attrs")
        if _SCRIPT_SRC_ATTR.search(attrs) is not None:
            continue
        type_match = _SCRIPT_TYPE_ATTR.search(attrs)
        if type_match is not None:
            script_type = (type_match.group("quoted") or type_match.group("bare") or "").strip()
            script_type = script_type.split(";", 1)[0].lower()
            if script_type and script_type not in _JAVASCRIPT_TYPES:
                continue
        bodies.append(match.group("body"))
    return tuple(bodies)


def _strip_javascript_comments(source: str) -> str:
    output: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            output.extend((" ", " "))
            index += 2
            while index < len(source) and source[index] not in {"\r", "\n"}:
                output.append(" ")
                index += 1
            continue
        if char == "/" and next_char == "*":
            output.extend((" ", " "))
            index += 2
            while index < len(source):
                if source[index] == "*" and index + 1 < len(source) and source[index + 1] == "/":
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(source[index] if source[index] in {"\r", "\n"} else " ")
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _is_static_url_candidate(url: str) -> bool:
    return not (
        "{{" in url
        or "~" in url
        or "{%" in url
        or url.startswith(("#", "javascript:"))
        or "://" in url
    )


def _confirm_method_for_match(source: str, match_start: int, match_end: int) -> str:
    window_start = max(0, match_start - 160)
    window_end = min(len(source), match_end + 160)
    window = source[window_start:window_end]
    method_match = _CONFIRM_METHOD_PATTERN.search(window)
    if method_match is None:
        return "POST"
    return method_match.group(1).upper()


def _is_kida_expression_continued(source: str, match_end: int) -> bool:
    next_source = source[match_end:].lstrip()
    return next_source.startswith("~")


def get_form_method(source: str, action_pos: int) -> str | None:
    """Return POST only when form has method='post', otherwise GET."""
    from collections import deque

    before = source[:action_pos]
    last_match = next(
        iter(deque(_FORM_OPEN_TAG.finditer(before), maxlen=1)),
        None,
    )
    if last_match is None:
        return None
    form_start = last_match.start()
    tag_end = source.find(">", form_start)
    if tag_end == -1 or tag_end < action_pos:
        return None
    form_tag = source[form_start:tag_end]
    if METHOD_POST.search(form_tag):
        return "POST"
    return "GET"


def extract_targets_from_source(source: str) -> list[tuple[str, str, str | None]]:
    """Extract (attr_name, url, method_override) from template source."""
    targets: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()

    def _append_target(attr_name: str, url: str, method_override: str | None) -> None:
        if not _is_static_url_candidate(url):
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

    for match in _CONFIRM_URL_PATTERN.finditer(source):
        if _is_kida_expression_continued(source, match.end()):
            continue
        url = match.group(1)
        method_override = _confirm_method_for_match(source, match.start(), match.end())
        _append_target("confirm_url", url, method_override)

    return targets


def extract_query_client_references(source: str) -> tuple[QueryClientReference, ...]:
    """Extract literal, browser-proven QUERY calls from template scripts.

    Chirp does not publish a declarative ``hx-query`` attribute. This scanner
    intentionally recognizes only the programmatic Fetch and ``htmx.ajax``
    forms covered by the QUERY browser contract, and only when the URL and
    method are literal. Dynamic headers remain unknown instead of becoming a
    false-positive media-type diagnostic.
    """
    references: list[QueryClientReference] = []
    seen: set[QueryClientReference] = set()

    for raw_script in _executable_script_bodies(source):
        script = _strip_javascript_comments(raw_script)
        for match in _HTMX_QUERY_PREFIX.finditer(script):
            options = _javascript_call_suffix(script, match.end())
            reference = _query_client_reference("htmx.ajax", match.group("url"), options)
            if reference not in seen:
                seen.add(reference)
                references.append(reference)

        for match in _FETCH_PREFIX.finditer(script):
            options = _javascript_call_suffix(script, match.end())
            if _QUERY_METHOD_OPTION.search(options) is None:
                continue
            reference = _query_client_reference("fetch", match.group("url"), options)
            if reference not in seen:
                seen.add(reference)
                references.append(reference)

    return tuple(references)


def extract_href_references(source: str) -> set[str]:
    """Extract URL paths from href= attributes and macro keyword arguments.

    Used for orphan-route detection: catches ``<a href="/team">``, macro calls
    like ``sidebar_link("/team", ...)``, and keyword args like ``href="/login"``.
    Returns base paths (query strings and fragments stripped).
    """
    urls: set[str] = set()
    for pattern in (_HREF_ATTR_PATTERN, _MACRO_URL_ARG_PATTERN, _POSITIONAL_URL_ARG_PATTERN):
        for m in pattern.finditer(source):
            url = m.group(1)
            if not _is_static_url_candidate(url):
                continue
            if not url.startswith("/"):
                continue
            base = url.split("?")[0].split("#")[0]
            if base:
                urls.add(base)
    return urls


def extract_legacy_action_contracts(source: str) -> set[str]:
    """Extract legacy action= contract names from template call arguments."""
    names: set[str] = set()
    for match in _LEGACY_ACTION_PATTERN.finditer(source):
        value = match.group(1).strip()
        if value and _is_static_url_candidate(value) and not value.startswith("/"):
            names.add(value)
    return names


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


def resolve_template_reference(
    reference: str,
    caller: str,
    template_aliases: Mapping[str, str] | None = None,
) -> str:
    """Resolve a Kida cross-template reference for contract bookkeeping.

    Kida 0.8 lets templates use ``./`` and ``../`` references relative to the
    caller, plus ``@alias/`` namespace prefixes. Chirp's contract rules compare
    references against the root-relative names returned by loaders, so keep the
    same canonicalization here.
    """
    if reference.startswith("@"):
        alias, sep, rest = reference[1:].partition("/")
        if sep and template_aliases and alias in template_aliases:
            root = template_aliases[alias].strip("/")
            return f"{root}/{rest}" if rest else root
        return reference

    from kida.exceptions import TemplateNotFoundError

    try:
        from kida.utils.template_keys import resolve_template_name as kida_resolve_template_name
    except ImportError:
        pass
    else:
        try:
            return kida_resolve_template_name(reference, caller=caller)
        except TemplateNotFoundError:
            return reference

    if not reference.startswith("."):
        return reference
    caller_dir = caller.rsplit("/", 1)[0] if "/" in caller else ""
    resolved = posixpath.normpath(posixpath.join(caller_dir, reference))
    if resolved.startswith("../"):
        return reference
    return resolved


def extract_fragment_island_ids(source: str) -> set[str]:
    """Extract id values from fragment_island() macro calls."""
    return {m.group(1) for m in _FRAGMENT_ISLAND_PATTERN.finditer(source)}


def extract_wizard_form_ids(source: str) -> set[str]:
    """Extract id values from wizard_form() macro calls."""
    return {m.group(1) for m in _WIZARD_FORM_PATTERN.finditer(source)}


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
    for val in _MUTATING_BLOCK_TARGET.findall(source):
        if "{{" not in val and "{%" not in val:
            ids.add(val.strip())
    for val in _TARGET_IN_MUTATING.findall(source):
        if "{{" not in val and "{%" not in val:
            ids.add(val.strip())
    return ids


def extract_htmx_partial_sources(source: str) -> list[str]:
    """Extract ``src=`` attribute values from ``<htmx-partial>`` elements.

    Values are normalized to URL paths suitable for route matching:
    query strings and fragments are stripped, and only leading-``/`` paths
    are kept.  Results are deduplicated while preserving order.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for m in _HTMX_PARTIAL_PATTERN.finditer(source):
        raw = m.group(1).strip()
        if not _is_static_url_candidate(raw):
            continue
        path = raw
        for sep in ("?", "#"):
            if sep in path:
                path = path.split(sep, 1)[0]
        if not path.startswith("/"):
            continue
        if path and path not in seen:
            seen.add(path)
            urls.append(path)
    return urls


def _load_one(loader: Any, name: str) -> tuple[str, str] | None:
    """Load a single template; returns (name, source) or None on error."""
    try:
        source, _ = loader.get_source(name)
        return (name, source)
    except Exception:
        return None


def load_template_sources(kida_env: Any) -> dict[str, str]:
    """Load all template sources from environment loader (parallel disk reads)."""
    sources: dict[str, str] = {}
    loader = kida_env.loader
    if loader is None:
        return sources
    list_fn = getattr(loader, "list_templates", None)
    if list_fn is None:
        return sources
    try:
        names = [n for n in list_fn() if n.endswith(_TEMPLATE_SOURCE_SUFFIXES)]
        if not names:
            return sources
        with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
            futures = {pool.submit(_load_one, loader, name): name for name in names}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    sources[result[0]] = result[1]
    except Exception:
        logging.getLogger("chirp.contracts").debug(
            "Template source loading failed during parallel scan",
            exc_info=True,
        )
    return sources

"""Fail-loud htmx provisioning and template-drift checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION, HtmxProvisioningManifest

from .types import ContractIssue, Severity

_SOURCE_VERSION = re.compile(r"htmx\.org@([^/]+)", re.IGNORECASE)
_QUEUE_MODIFIER = re.compile(r"(?:^|\s)queue:(?:all|first|last|none)(?=\s|$)", re.IGNORECASE)
_SERVER_ERROR_STATUS = re.compile(r"^hx-status:(?:5\d\d|5xx|5x\d|5\dx)$", re.IGNORECASE)
_IGNORED_ELEMENTS = frozenset({"code", "pre"})
_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_REQUEST_ATTRIBUTES = frozenset(
    {"hx-delete", "hx-get", "hx-patch", "hx-post", "hx-put", "hx-action"}
)
_INHERITABLE_ATTRIBUTES = frozenset(
    {
        "hx-boost",
        "hx-confirm",
        "hx-disabled-elt",
        "hx-encoding",
        "hx-headers",
        "hx-include",
        "hx-indicator",
        "hx-push-url",
        "hx-replace-url",
        "hx-select",
        "hx-select-oob",
        "hx-swap",
        "hx-sync",
        "hx-target",
        "hx-vals",
    }
)

# htmx 2 constructs accepted during the preview only because Chirp provisions
# htmx-2-compat. They are migration debt, not immediate browser failures.
_HTMX2_ATTRIBUTE_MIGRATIONS: dict[str, tuple[str, str]] = {
    "hx-disabled-elt": (
        "htmx 4 renamed this attribute",
        "rename it to 'hx-disable' after renaming any htmx 2 'hx-disable' to 'hx-ignore'",
    ),
    "hx-vars": ("htmx 4 removed this attribute", "use 'hx-vals' with the 'js:' prefix"),
    "hx-params": (
        "htmx 4 removed this attribute",
        "configure parameters in the 'htmx:config:request' event",
    ),
    "hx-prompt": ("htmx 4 moved prompting out of core", "load the hx-prompt extension"),
    "hx-ext": ("htmx 4 removed per-element extension activation", "load extensions directly"),
    "hx-disinherit": (
        "htmx 4 removed this implicit-inheritance control",
        "remove it and add ':inherited' only where inheritance is intended",
    ),
    "hx-inherit": (
        "htmx 4 removed this implicit-inheritance control",
        "remove it and add ':inherited' only where inheritance is intended",
    ),
    "hx-request": ("htmx 4 removed this attribute", "rename it to 'hx-config'"),
    "hx-history": (
        "htmx 4 removed the localStorage history cache",
        "remove it and select reload or refetch behavior with 'htmx.config.history'",
    ),
}
_HTMX4_ONLY_ATTRIBUTES = frozenset({"hx-action", "hx-config", "hx-ignore", "hx-method"})

_EXTENSION_EVENT_RENAMES: dict[str, str] = {
    "htmx:sseOpen": "htmx:after:sse:connection",
    "htmx:sseError": "htmx:sse:error",
    "htmx:sseBeforeMessage": "htmx:before:sse:message",
    "htmx:sseMessage": "htmx:after:sse:message",
    "htmx:sseClose": "htmx:sse:close",
    "htmx:wsOpen": "htmx:after:ws:connection",
    "htmx:wsClose": "htmx:ws:close",
    "htmx:wsConfigSend": "htmx:before:ws:request",
    "htmx:wsBeforeSend": "htmx:before:ws:request",
    "htmx:wsAfterSend": "htmx:after:ws:request",
    "htmx:wsBeforeMessage": "htmx:before:ws:message",
    "htmx:wsAfterMessage": "htmx:after:ws:message",
}

_HTMX2_EVENT_RENAMES: dict[str, str] = {
    "htmx:afterOnLoad": "htmx:after:init",
    "htmx:afterProcessNode": "htmx:after:init",
    "htmx:afterRequest": "htmx:after:request",
    "htmx:afterSettle": "htmx:after:swap",
    "htmx:afterSwap": "htmx:after:swap",
    "htmx:beforeCleanupElement": "htmx:before:cleanup",
    "htmx:beforeHistorySave": "htmx:before:history:update",
    "htmx:beforeOnLoad": "htmx:before:init",
    "htmx:beforeProcessNode": "htmx:before:process",
    "htmx:beforeRequest": "htmx:before:request",
    "htmx:beforeSwap": "htmx:before:swap",
    "htmx:configRequest": "htmx:config:request",
    "htmx:historyCacheMiss": "htmx:before:history:restore",
    "htmx:historyRestore": "htmx:before:history:restore",
    "htmx:load": "htmx:after:init",
    "htmx:oobAfterSwap": "htmx:after:swap",
    "htmx:oobBeforeSwap": "htmx:before:swap",
    "htmx:pushedIntoHistory": "htmx:after:history:push",
    "htmx:replacedInHistory": "htmx:after:history:replace",
    "htmx:responseError": "htmx:response:error",
    "htmx:sendError": "htmx:error",
    "htmx:swapError": "htmx:error",
    "htmx:targetError": "htmx:error",
    "htmx:timeout": "htmx:error",
}
_HTMX2_REMOVED_EVENTS = frozenset(
    {
        "htmx:validation:validate",
        "htmx:validation:failed",
        "htmx:validation:halted",
        "htmx:xhr:loadstart",
        "htmx:xhr:loadend",
        "htmx:xhr:progress",
        "htmx:xhr:abort",
    }
)
_HTMX2_CONFIG_RENAMES: dict[str, str] = {
    "defaultSwapStyle": "defaultSwap",
    "globalViewTransitions": "transitions",
    "historyEnabled": "history",
    "includeIndicatorStyles": "includeIndicatorCSS",
    "timeout": "defaultTimeout",
}
_HTMX2_REMOVED_CONFIG: dict[str, str] = {
    "allowEval": "remove it and review htmx 4's CSP-safe defaults",
    "allowNestedOobSwaps": "remove it and make nested OOB behavior explicit in response markup",
    "allowScriptTags": "remove it and use the htmx 4 script policy",
    "disableSelector": "replace the selector with 'hx-ignore' on the intended region",
    "historyCacheSize": "remove it because htmx 4 no longer has a localStorage history cache",
    "responseHandling": "replace it with 'hx-status:*' attributes and 'htmx.config.noSwap'",
    "selfRequestsOnly": "rename the policy to 'htmx.config.mode'",
    "withCredentials": "move the setting to per-element 'hx-config'",
}


@dataclass(frozen=True, slots=True)
class _Script:
    index: int
    document_index: int
    line: int
    src: str
    marker: str | None
    role: str | None
    tier: str | None
    version: str | None

    @property
    def source_version(self) -> str | None:
        match = _SOURCE_VERSION.search(self.src)
        return match.group(1) if match is not None else None

    @property
    def source_role(self) -> str | None:
        if "htmx-2-compat" in self.src:
            return "compat"
        if re.search(r"(?:^|/)hx-sse(?:\.min)?\.js(?:$|[?#])", self.src):
            return "sse"
        if re.search(r"(?:^|/)htmx(?:\.min)?\.js(?:$|[?#])", self.src):
            return "core"
        return None


@dataclass(frozen=True, slots=True)
class _Attribute:
    tag: str
    line: int
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class _InlineScript:
    line: int
    source: str


@dataclass(frozen=True, slots=True)
class _InheritanceUse:
    line: int
    ancestor_line: int
    attribute: str
    request_attribute: str


@dataclass(frozen=True, slots=True)
class _Element:
    tag: str
    line: int
    attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Tag:
    tag: str
    line: int
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _DeleteUse:
    line: int
    form_line: int
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _HtmxConfig:
    document_index: int
    line: int
    content: str
    marker: str | None
    tier: str | None
    version: str | None


class _TemplateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[_Script] = []
        self.attributes: list[_Attribute] = []
        self.inline_scripts: list[_InlineScript] = []
        self.inheritance_uses: list[_InheritanceUse] = []
        self.tags: list[_Tag] = []
        self.delete_uses: list[_DeleteUse] = []
        self.form_controls: dict[int, set[str]] = {}
        self.htmx_configs: list[_HtmxConfig] = []
        self._elements: list[_Element] = []
        self._ignored_depth = 0
        self._inline_script = False
        self._inheritance_seen: set[tuple[int, str]] = set()
        self._document_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _IGNORED_ELEMENTS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return

        line = self.getpos()[0]
        document_index = self._document_index
        self._document_index += 1
        values = {name.lower(): value or "" for name, value in attrs}
        attribute_names = tuple(values)
        attribute_items = tuple(values.items())
        self.tags.append(_Tag(tag, line, attribute_items))
        if tag == "meta" and values.get("name", "").lower() == "htmx-config":
            self.htmx_configs.append(
                _HtmxConfig(
                    document_index=document_index,
                    line=line,
                    content=values.get("content", ""),
                    marker=values.get("data-chirp") or None,
                    tier=values.get("data-chirp-htmx-tier") or None,
                    version=values.get("data-chirp-htmx-version") or None,
                )
            )
        for name, value in values.items():
            if name.startswith(("hx-", "sse-", "ws-")):
                self.attributes.append(_Attribute(tag, line, name, value))

        request_attribute = next(
            (name for name in attribute_names if name in _REQUEST_ATTRIBUTES),
            None,
        )
        if request_attribute is None and tag in {"a", "form"}:
            request_attribute = f"boosted <{tag}>"
        if request_attribute is not None:
            shadowed = set(attribute_names)
            for element in reversed(self._elements):
                for name in element.attributes:
                    relevant = name in _INHERITABLE_ATTRIBUTES and (
                        not request_attribute.startswith("boosted") or name == "hx-boost"
                    )
                    key = (element.line, name)
                    if relevant and name not in shadowed and key not in self._inheritance_seen:
                        self.inheritance_uses.append(
                            _InheritanceUse(line, element.line, name, request_attribute)
                        )
                        self._inheritance_seen.add(key)
                    shadowed.add(name)

        form = next(
            (element for element in reversed(self._elements) if element.tag == "form"), None
        )
        if form is not None:
            if tag in {"input", "select", "textarea"}:
                control_name = values.get("name")
                if control_name and "disabled" not in values:
                    self.form_controls.setdefault(form.line, set()).add(control_name)
            if "hx-delete" in values:
                self.delete_uses.append(_DeleteUse(line, form.line, attribute_items))

        if tag != "script":
            if tag not in _VOID_ELEMENTS:
                self._elements.append(_Element(tag, line, attribute_names))
            return

        src = values.get("src", "")
        self._inline_script = not src
        marker = values.get("data-chirp") or None
        extension = values.get("data-chirp-htmx-extension") or None
        role: str | None = None
        if marker == "htmx" or re.search(r"(?:^|/)htmx(?:\.min)?\.js(?:$|[?#])", src):
            role = "core"
        elif marker == "htmx-extension":
            role = extension or "unknown"
        elif "htmx-2-compat" in src:
            role = "compat"
        elif re.search(r"(?:^|/)hx-sse(?:\.min)?\.js(?:$|[?#])", src):
            role = "sse"
        if role is None:
            return
        self.scripts.append(
            _Script(
                index=len(self.scripts),
                document_index=document_index,
                line=line,
                src=src,
                marker=marker,
                role=role,
                tier=values.get("data-chirp-htmx-tier") or None,
                version=values.get("data-chirp-htmx-version") or None,
            )
        )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._ignored_depth:
            if tag in _IGNORED_ELEMENTS:
                self._ignored_depth -= 1
            return
        if tag == "script":
            self._inline_script = False
        for index in range(len(self._elements) - 1, -1, -1):
            if self._elements[index].tag == tag:
                del self._elements[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._inline_script and data.strip():
            self.inline_scripts.append(_InlineScript(self.getpos()[0], data))


def _issue(
    template: str,
    message: str,
    *,
    line: int | None = None,
    severity: Severity = Severity.ERROR,
) -> ContractIssue:
    details = f"Detected at line {line}." if line is not None else None
    return ContractIssue(
        severity=severity,
        category="htmx_compatibility",
        message=message,
        template=template,
        details=details,
    )


def _parse_template(source: str) -> _TemplateParser:
    parser = _TemplateParser()
    parser.feed(source)
    return parser


def _drift_issue(
    template: str,
    *,
    tier: str,
    construct: str,
    consequence: str,
    remediation: str,
    line: int,
    severity: Severity,
) -> ContractIssue:
    return _issue(
        template,
        f"Configured tier {tier!r} found construct {construct!r}. {consequence}. "
        f"Remediation: {remediation}.",
        line=line,
        severity=severity,
    )


def _without_javascript_comments(source: str) -> str:
    """Blank JS comments while preserving strings and line numbers."""
    output: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
                output.append(char)
            else:
                output.append(" ")
        elif block_comment:
            if char == "*" and following == "/":
                output.extend((" ", " "))
                index += 1
                block_comment = False
            else:
                output.append("\n" if char == "\n" else " ")
        elif quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"', "`"}:
            quote = char
            output.append(char)
        elif char == "/" and following == "/":
            output.extend((" ", " "))
            index += 1
            line_comment = True
        elif char == "/" and following == "*":
            output.extend((" ", " "))
            index += 1
            block_comment = True
        else:
            output.append(char)
        index += 1
    return "".join(output)


def _inline_occurrences(
    parsed: _TemplateParser,
    constructs: set[str] | frozenset[str],
) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for script in parsed.inline_scripts:
        source = _without_javascript_comments(script.source)
        for offset, line_source in enumerate(source.splitlines()):
            for construct in constructs:
                key = (script.line + offset, construct)
                if construct in line_source and key not in seen:
                    seen.add(key)
                    found.append(key)
    for attribute in parsed.attributes:
        source = f"{attribute.name} {attribute.value}".lower()
        for construct in constructs:
            key = (attribute.line, construct)
            if construct.lower() in source and key not in seen:
                seen.add(key)
                found.append(key)
    return found


def _effective_tier(
    manifest: HtmxProvisioningManifest,
    scripts: list[_Script],
) -> str | None:
    if manifest.enabled:
        return manifest.tier
    marked = [item for item in scripts if item.marker in {"htmx", "htmx-extension"}]
    if any(
        item.tier == "4-preview"
        or item.version == HTMX4_PREVIEW_VERSION
        or (item.source_version or "").startswith("4.")
        for item in marked
    ):
        return "4-preview"
    if any(
        item.tier == "2-managed"
        or (item.version or item.source_version or "").startswith(("1.", "2."))
        for item in marked
        if item.role == "core"
    ):
        return "2-managed"
    return None


def _check_template_drift(
    template: str,
    parsed: _TemplateParser,
    tier: str | None,
) -> list[ContractIssue]:
    if tier is None:
        return []
    issues: list[ContractIssue] = []
    if tier == "4-preview":
        for attribute in parsed.attributes:
            if attribute.name in {"sse-connect", "sse-swap"}:
                issues.append(
                    _drift_issue(
                        template,
                        tier=tier,
                        construct=attribute.name,
                        consequence="htmx 4's SSE extension ignores the htmx 2 attribute, so updates stop",
                        remediation="use 'hx-sse:connect' and htmx 4 SSE event handling",
                        line=attribute.line,
                        severity=Severity.ERROR,
                    )
                )
            elif attribute.name in {"ws-connect", "ws-send"}:
                replacement = attribute.name.replace("ws-", "hx-ws:", 1)
                issues.append(
                    _drift_issue(
                        template,
                        tier=tier,
                        construct=attribute.name,
                        consequence="htmx 4's WebSocket extension ignores the htmx 2 attribute",
                        remediation=f"rename it to '{replacement}' and load the htmx 4 extension",
                        line=attribute.line,
                        severity=Severity.ERROR,
                    )
                )
            elif attribute.name == "hx-disable":
                issues.append(
                    _drift_issue(
                        template,
                        tier=tier,
                        construct=attribute.name,
                        consequence=(
                            "the name changed meaning from ignoring a subtree to disabling controls, "
                            "so browser behavior is ambiguous"
                        ),
                        remediation="rename the htmx 2 use to 'hx-ignore' before previewing htmx 4",
                        line=attribute.line,
                        severity=Severity.ERROR,
                    )
                )
            elif attribute.name in _HTMX2_ATTRIBUTE_MIGRATIONS:
                consequence, remediation = _HTMX2_ATTRIBUTE_MIGRATIONS[attribute.name]
                issues.append(
                    _drift_issue(
                        template,
                        tier=tier,
                        construct=attribute.name,
                        consequence=(
                            f"{consequence}; compatibility mode may preserve current behavior, "
                            "but removing htmx-2-compat will expose the drift"
                        ),
                        remediation=remediation,
                        line=attribute.line,
                        severity=Severity.WARNING,
                    )
                )

        issues.extend(
            [
                _drift_issue(
                    template,
                    tier=tier,
                    construct=f"implicit {use.attribute} inheritance",
                    consequence=(
                        f"{use.request_attribute} at line {use.line} depends on an ancestor at "
                        f"line {use.ancestor_line}; htmx-2-compat preserves that dependency only "
                        "during migration"
                    ),
                    remediation=f"rename the ancestor attribute to '{use.attribute}:inherited'",
                    line=use.line,
                    severity=Severity.WARNING,
                )
                for use in parsed.inheritance_uses
            ]
        )

        for line, event in _inline_occurrences(parsed, set(_HTMX2_EVENT_RENAMES)):
            replacement = _HTMX2_EVENT_RENAMES[event]
            issues.append(
                _drift_issue(
                    template,
                    tier=tier,
                    construct=event,
                    consequence="htmx-2-compat re-emits this old event name only during migration",
                    remediation=f"listen for '{replacement}'",
                    line=line,
                    severity=Severity.WARNING,
                )
            )
        removed_events = _HTMX2_REMOVED_EVENTS | frozenset(_EXTENSION_EVENT_RENAMES)
        for line, event in _inline_occurrences(parsed, removed_events):
            replacement = _EXTENSION_EVENT_RENAMES.get(event)
            issues.append(
                _drift_issue(
                    template,
                    tier=tier,
                    construct=event,
                    consequence="htmx 4 removed this event and compatibility mode does not restore it",
                    remediation=(
                        f"listen for '{replacement}'"
                        if replacement is not None
                        else "use native browser validation/fetch events or the documented htmx 4 lifecycle"
                    ),
                    line=line,
                    severity=Severity.ERROR,
                )
            )
        for script in parsed.inline_scripts:
            source = _without_javascript_comments(script.source)
            for offset, line_source in enumerate(source.splitlines()):
                for old_name, replacement in _HTMX2_CONFIG_RENAMES.items():
                    if re.search(rf"\bhtmx\.config\.{re.escape(old_name)}\b", line_source):
                        issues.append(
                            _drift_issue(
                                template,
                                tier=tier,
                                construct=f"htmx.config.{old_name}",
                                consequence="htmx 4 renamed this configuration key",
                                remediation=f"use 'htmx.config.{replacement}'",
                                line=script.line + offset,
                                severity=Severity.WARNING,
                            )
                        )
                for old_name, remediation in _HTMX2_REMOVED_CONFIG.items():
                    if re.search(rf"\bhtmx\.config\.{re.escape(old_name)}\b", line_source):
                        issues.append(
                            _drift_issue(
                                template,
                                tier=tier,
                                construct=f"htmx.config.{old_name}",
                                consequence="htmx 4 removed this configuration key",
                                remediation=remediation,
                                line=script.line + offset,
                                severity=Severity.WARNING,
                            )
                        )
        return issues

    for attribute in parsed.attributes:
        htmx4_only = (
            attribute.name in _HTMX4_ONLY_ATTRIBUTES
            or attribute.name.startswith(("hx-sse:", "hx-status:", "hx-ws:"))
            or ":inherited" in attribute.name
            or ":append" in attribute.name
        )
        if not htmx4_only:
            continue
        issues.append(
            _drift_issue(
                template,
                tier=tier,
                construct=attribute.name,
                consequence="htmx 2 does not implement this htmx 4 construct, so the behavior is inert",
                remediation="use the htmx 2 equivalent or select the exact htmx 4 preview tier",
                line=attribute.line,
                severity=Severity.ERROR,
            )
        )

    htmx4_events = set(_HTMX2_EVENT_RENAMES.values()) | {"htmx:finally:request"}
    for line, event in _inline_occurrences(parsed, htmx4_events):
        issues.append(
            _drift_issue(
                template,
                tier=tier,
                construct=event,
                consequence="htmx 2 does not emit this htmx 4 lifecycle event",
                remediation="listen for the htmx 2 event name or select the preview tier",
                line=line,
                severity=Severity.ERROR,
            )
        )
    return issues


def _check_default_contract_drift(
    template: str,
    parsed: _TemplateParser,
    tier: str | None,
) -> list[ContractIssue]:
    if tier != "4-preview":
        return []
    issues: list[ContractIssue] = []
    issues.extend(
        [
            _drift_issue(
                template,
                tier=tier,
                construct=f'hx-trigger="{attribute.value}"',
                consequence=(
                    "htmx 4 removed trigger queue modifiers, so the intended mutation "
                    "serialization is silently lost"
                ),
                remediation="remove queue:* and add hx-sync with an explicit queue strategy",
                line=attribute.line,
                severity=Severity.ERROR,
            )
            for attribute in parsed.attributes
            if attribute.name == "hx-trigger" and _QUEUE_MODIFIER.search(attribute.value)
        ]
    )

    for delete in parsed.delete_uses:
        attributes = dict(delete.attributes)
        if attributes.get("hx-include"):
            continue
        controls = parsed.form_controls.get(delete.form_line, set())
        if not controls:
            continue
        csrf_control = next((name for name in controls if "csrf" in name.lower()), None)
        severity = Severity.ERROR if csrf_control is not None else Severity.WARNING
        consequence = (
            f"htmx 4 excludes enclosing form controls from DELETE, including CSRF field "
            f"{csrf_control!r}, so the request can fail protection"
            if csrf_control is not None
            else "htmx 4 excludes enclosing form controls from DELETE, so named values are not sent"
        )
        issues.append(
            _drift_issue(
                template,
                tier=tier,
                construct="hx-delete inside a form without hx-include",
                consequence=consequence,
                remediation='add hx-include="closest form" or put required values in the URL',
                line=delete.line,
                severity=severity,
            )
        )

    history_elements = [item for item in parsed.attributes if item.name == "hx-history-elt"]
    pushed_history = [
        item
        for item in parsed.attributes
        if item.name in {"hx-push-url", "hx-replace-url"}
        and item.value.strip().lower() not in {"", "false"}
    ]
    if pushed_history and not history_elements:
        first = pushed_history[0]
        issues.append(
            _drift_issue(
                template,
                tier=tier,
                construct=first.name,
                consequence=(
                    "htmx 4 refetches history without a localStorage cache, and no stable "
                    "hx-history-elt restore boundary is declared"
                ),
                remediation="declare one stable hx-history-elt in the shell or use full-page history",
                line=first.line,
                severity=Severity.WARNING,
            )
        )

    static_ids = {
        attributes["id"] for tag in parsed.tags if (attributes := dict(tag.attributes)).get("id")
    }
    broad_ids = {
        attributes["id"]
        for tag in parsed.tags
        if tag.tag in {"body", "main"} and (attributes := dict(tag.attributes)).get("id")
    }
    for tag in parsed.tags:
        attributes = dict(tag.attributes)
        for name, value in tag.attributes:
            if _SERVER_ERROR_STATUS.match(name) is None or "swap:none" in value.lower():
                continue
            target = attributes.get("hx-target", "this").strip()
            target_id = target.removeprefix("#") if target.startswith("#") else None
            unsafe = target in {"body", "html"} or target_id in broad_ids
            unresolved = target_id is not None and target_id not in static_ids
            if not unsafe and not unresolved:
                continue
            reason = "broad shell target" if unsafe else "unresolved target"
            issues.append(
                _drift_issue(
                    template,
                    tier=tier,
                    construct=name,
                    consequence=(
                        f"the explicit 5xx swap uses a {reason} {target!r}, so a production "
                        "failure can erase visible application UI"
                    ),
                    remediation="target a statically present local error region or use swap:none",
                    line=tag.line,
                    severity=Severity.ERROR,
                )
            )
    return issues


def _check_preview_bundle(
    template: str,
    scripts: list[_Script],
    configs: list[_HtmxConfig],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    if not configs:
        issues.append(
            _issue(
                template,
                "Htmx 4 preview bundle is missing its htmx-config policy metadata. Add the "
                "marked noSwap/defaultTimeout/compat policy before core, or use managed injection.",
            )
        )
    elif len(configs) > 1:
        issues.append(
            _issue(
                template,
                f"Htmx 4 preview bundle declares {len(configs)} htmx-config policies; "
                "the browser contract must be declared exactly once.",
                line=configs[1].line,
            )
        )
    if configs:
        config = configs[0]
        if config.marker != "htmx-config":
            issues.append(
                _issue(
                    template,
                    "Htmx 4 policy metadata lacks data-chirp='htmx-config'; add the marker "
                    "so compatibility checks can verify the selected defaults.",
                    line=config.line,
                )
            )
        if config.tier != "4-preview" or config.version != HTMX4_PREVIEW_VERSION:
            issues.append(
                _issue(
                    template,
                    "Htmx 4 policy metadata must declare tier '4-preview' and exact version "
                    f"{HTMX4_PREVIEW_VERSION!r}.",
                    line=config.line,
                )
            )
        try:
            payload = json.loads(config.content)
        except TypeError, ValueError:
            payload = None
        valid_policy = (
            isinstance(payload, dict)
            and payload.get("noSwap") == [204, 304, "5xx"]
            and payload.get("defaultTimeout") == 60_000
            and isinstance(payload.get("compat"), dict)
            and payload["compat"].get("swapErrorResponseCodes") is True
        )
        if not valid_policy:
            issues.append(
                _issue(
                    template,
                    "Htmx 4 policy metadata disagrees with Chirp's accepted defaults. Set "
                    "noSwap to [204,304,'5xx'], defaultTimeout to 60000, and "
                    "compat.swapErrorResponseCodes to true.",
                    line=config.line,
                )
            )
        if scripts and config.document_index > min(item.document_index for item in scripts):
            issues.append(
                _issue(
                    template,
                    "Htmx 4 policy metadata appears after a preview script. Move htmx-config "
                    "before core so initialization cannot observe upstream defaults.",
                    line=config.line,
                )
            )
    by_role = {
        role: [item for item in scripts if item.role == role] for role in ("core", "compat", "sse")
    }
    for role, items in by_role.items():
        if not items:
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 preview bundle is missing the {role!r} script. Include core, "
                    "htmx-2-compat, and hx-sse in that order, or roll back to htmx 2.0.10.",
                )
            )
        elif len(items) > 1:
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 preview bundle declares {len(items)} {role!r} scripts; each role "
                    "must load exactly once.",
                    line=items[1].line,
                )
            )

    for item in scripts:
        expected_marker = "htmx" if item.role == "core" else "htmx-extension"
        if item.marker != expected_marker:
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 {item.role!r} script lacks data-chirp={expected_marker!r}; "
                    "add the marker so managed injection and compatibility checks cannot mix bundles.",
                    line=item.line,
                )
            )
        if item.tier != "4-preview":
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 {item.role!r} script must declare data-chirp-htmx-tier='4-preview'.",
                    line=item.line,
                )
            )
        if item.source_role is not None and item.source_role != item.role:
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 script declares role {item.role!r} but its source is the "
                    f"{item.source_role!r} asset. Align data-chirp role metadata with the file.",
                    line=item.line,
                )
            )
        versions = {value for value in (item.version, item.source_version) if value is not None}
        if versions != {HTMX4_PREVIEW_VERSION}:
            issues.append(
                _issue(
                    template,
                    f"Htmx 4 {item.role!r} script must use and declare the exact preview pin "
                    f"{HTMX4_PREVIEW_VERSION!r}; detected {sorted(versions)!r}.",
                    line=item.line,
                )
            )

    if all(len(by_role[role]) == 1 for role in ("core", "compat", "sse")):
        observed = [by_role[role][0].index for role in ("core", "compat", "sse")]
        if observed != sorted(observed):
            issues.append(
                _issue(
                    template,
                    "Htmx 4 preview scripts are out of order. Load core, htmx-2-compat, then "
                    "hx-sse so classic defer execution preserves compatibility.",
                    line=min(item.line for item in scripts),
                )
            )
    return issues


def check_htmx_compatibility(
    template_sources: dict[str, str],
    manifest: HtmxProvisioningManifest,
) -> list[ContractIssue]:
    """Detect statically provable mixed or incomplete htmx provisioning."""
    issues: list[ContractIssue] = []
    for template in sorted(template_sources):
        if template.startswith(("chirp/", "chirpui/")):
            continue
        source = template_sources[template]
        parsed = _parse_template(source)
        scripts = parsed.scripts
        marked = [item for item in scripts if item.marker in {"htmx", "htmx-extension"}]
        effective_tier = _effective_tier(manifest, scripts)
        issues.extend(_check_template_drift(template, parsed, effective_tier))
        issues.extend(_check_default_contract_drift(template, parsed, effective_tier))

        if not scripts:
            continue

        if manifest.enabled:
            unmarked_core = next(
                (item for item in scripts if item.role == "core" and item.marker != "htmx"),
                None,
            )
            if unmarked_core is not None:
                issues.append(
                    _issue(
                        template,
                        "Template loads htmx core without data-chirp='htmx' while managed "
                        "injection is enabled, so the client would load twice. Add the marker "
                        "and own the complete bundle, or remove the manual script.",
                        line=unmarked_core.line,
                    )
                )

        preview_observed = effective_tier == "4-preview"
        if preview_observed and (manifest.enabled or marked):
            issues.extend(_check_preview_bundle(template, scripts, parsed.htmx_configs))
            continue

        if manifest.tier != "2-managed":
            # Legacy marked self-hosted htmx 2 remains accepted. Preview
            # self-hosting opts into the strict branch through its metadata.
            continue

        for item in scripts:
            if item.role != "core":
                issues.append(
                    _issue(
                        template,
                        f"Htmx 2 managed tier found unexpected {item.role!r} preview extension.",
                        line=item.line,
                    )
                )
                continue
            detected = item.version or item.source_version
            if detected is not None and detected != manifest.version:
                issues.append(
                    _issue(
                        template,
                        f"Template htmx core version {detected!r} disagrees with configured "
                        f"version {manifest.version!r}. Align the script or remove it for managed injection.",
                        line=item.line,
                    )
                )
            if item.tier is not None and item.tier != "2-managed":
                issues.append(
                    _issue(
                        template,
                        f"Template htmx tier {item.tier!r} disagrees with configured tier '2-managed'.",
                        line=item.line,
                    )
                )
    return issues

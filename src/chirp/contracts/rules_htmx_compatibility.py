"""Fail-loud htmx provisioning compatibility checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION, HtmxProvisioningManifest

from .types import ContractIssue, Severity

_SOURCE_VERSION = re.compile(r"htmx\.org@([^/]+)", re.IGNORECASE)
_HTMX4_SSE_ATTR = re.compile(r"(?<![\w-])hx-sse:(?:connect|close)\s*=", re.IGNORECASE)
_LEGACY_SSE_ATTR = re.compile(r"(?<![\w-])sse-(?:connect|swap)\s*=", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Script:
    index: int
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


class _ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[_Script] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        src = values.get("src", "")
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
                line=self.getpos()[0],
                src=src,
                marker=marker,
                role=role,
                tier=values.get("data-chirp-htmx-tier") or None,
                version=values.get("data-chirp-htmx-version") or None,
            )
        )


def _issue(template: str, message: str, *, line: int | None = None) -> ContractIssue:
    details = f"Detected at line {line}." if line is not None else None
    return ContractIssue(
        severity=Severity.ERROR,
        category="htmx_compatibility",
        message=message,
        template=template,
        details=details,
    )


def _parse_scripts(source: str) -> list[_Script]:
    parser = _ScriptParser()
    parser.feed(source)
    return parser.scripts


def _check_preview_bundle(
    template: str,
    scripts: list[_Script],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
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
        scripts = _parse_scripts(source)
        marked = [item for item in scripts if item.marker in {"htmx", "htmx-extension"}]

        if manifest.tier == "2-managed" and _HTMX4_SSE_ATTR.search(source):
            issues.append(
                _issue(
                    template,
                    "Template uses htmx 4 hx-sse:* markup while the configured tier is htmx 2. "
                    "Select the exact 4.0.0-beta5 preview or use htmx 2 SSE attributes.",
                )
            )
        if manifest.tier == "4-preview" and _LEGACY_SSE_ATTR.search(source):
            issues.append(
                _issue(
                    template,
                    "Template uses removed sse-* markup under the htmx 4 preview. Migrate to "
                    "hx-sse:connect/hx-sse:close before enabling preview.",
                )
            )

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

        preview_observed = manifest.tier == "4-preview" or any(
            item.tier == "4-preview"
            or item.version == HTMX4_PREVIEW_VERSION
            or (item.source_version or "").startswith("4.")
            for item in marked
        )
        if preview_observed and (manifest.enabled or marked):
            issues.extend(_check_preview_bundle(template, scripts))
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

"""Island mount metadata checks."""

import html
import json
import re

from .types import ContractIssue, Severity

_ISLAND_TAG_PATTERN = re.compile(r"<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*)>", re.IGNORECASE)
_ID_PATTERN = re.compile(r'\bid\s*=\s*["\']([^"\']*)["\']')
_ISLAND_NAME_PATTERN = re.compile(r"\bdata-island\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_ISLAND_PROPS_PATTERN = re.compile(
    r"\bdata-island-props\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_ISLAND_VERSION_PATTERN = re.compile(
    r"\bdata-island-version\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_ISLAND_SRC_PATTERN = re.compile(r"\bdata-island-src\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_ISLAND_PRIMITIVE_PATTERN = re.compile(
    r"\bdata-island-primitive\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_ISLAND_VERSION_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_ISLAND_PRIMITIVE_REQUIRED_KEYS: dict[str, frozenset[str]] = {
    "state_sync": frozenset({"stateKey"}),
    "action_queue": frozenset({"actionId"}),
    "draft_store": frozenset({"draftKey"}),
    "error_boundary": frozenset(),
    "grid_state": frozenset({"stateKey", "columns"}),
    "wizard_state": frozenset({"stateKey", "steps"}),
    "upload_state": frozenset({"stateKey", "endpoint"}),
}


def extract_island_mounts(source: str) -> list[dict[str, str | None]]:
    """Extract island mount metadata from template HTML."""
    mounts: list[dict[str, str | None]] = []
    for match in _ISLAND_TAG_PATTERN.finditer(source):
        attrs = match.group("attrs")
        name_match = _ISLAND_NAME_PATTERN.search(attrs)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        id_match = _ID_PATTERN.search(attrs)
        props_match = _ISLAND_PROPS_PATTERN.search(attrs)
        version_match = _ISLAND_VERSION_PATTERN.search(attrs)
        src_match = _ISLAND_SRC_PATTERN.search(attrs)
        primitive_match = _ISLAND_PRIMITIVE_PATTERN.search(attrs)
        mounts.append(
            {
                "name": name or None,
                "mount_id": id_match.group(1).strip() if id_match else None,
                "props_raw": props_match.group(1) if props_match else None,
                "version": version_match.group(1).strip() if version_match else None,
                "src": src_match.group(1).strip() if src_match else None,
                "primitive": primitive_match.group(1).strip() if primitive_match else None,
            }
        )
    return mounts


def check_island_mounts(template_sources: dict[str, str], *, strict: bool) -> list[ContractIssue]:
    """Validate framework-agnostic island mount metadata in templates."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for mount in extract_island_mounts(source):
            name = mount["name"]
            if not name:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="islands",
                        message="Found data-island mount without a component name.",
                        template=template_name,
                    )
                )
                continue

            props_raw = mount["props_raw"]
            if props_raw is not None and "{{" not in props_raw and "{%" not in props_raw:
                decoded = html.unescape(props_raw)
                try:
                    parsed = json.loads(decoded)
                except Exception:
                    issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="islands",
                            message=f"Island '{name}' has malformed data-island-props JSON.",
                            template=template_name,
                            details=f"raw={props_raw!r}",
                        )
                    )
                else:
                    if not isinstance(parsed, (dict, list, str, int, float, bool, type(None))):
                        issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="islands",
                                message=f"Island '{name}' uses unsupported props JSON type.",
                                template=template_name,
                            )
                        )
                    else:
                        primitive_name = mount["primitive"] or name
                        required = _ISLAND_PRIMITIVE_REQUIRED_KEYS.get(primitive_name)
                        if required is not None:
                            if not isinstance(parsed, dict):
                                issues.append(
                                    ContractIssue(
                                        severity=Severity.ERROR,
                                        category="islands",
                                        message=(
                                            f"Island '{name}' primitive '{primitive_name}' "
                                            "expects object-like props."
                                        ),
                                        template=template_name,
                                    )
                                )
                            else:
                                missing = sorted(required - set(parsed))
                                if missing:
                                    issues.append(
                                        ContractIssue(
                                            severity=Severity.ERROR,
                                            category="islands",
                                            message=(
                                                f"Island '{name}' primitive '{primitive_name}' "
                                                f"is missing required props: {', '.join(missing)}."
                                            ),
                                            template=template_name,
                                        )
                                    )

            if strict and not mount["mount_id"]:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="islands",
                        message=(
                            f"Island '{name}' has no stable mount id. "
                            "Add id=... for deterministic remount targeting."
                        ),
                        template=template_name,
                    )
                )

            version = mount["version"]
            if strict and not version:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="islands",
                        message=(
                            f"Island '{name}' has no data-island-version. "
                            "Add a version to keep mount/runtime compatibility explicit."
                        ),
                        template=template_name,
                    )
                )
            if version and not _ISLAND_VERSION_VALUE_PATTERN.match(version):
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="islands",
                        message=(
                            f"Island '{name}' uses invalid data-island-version '{version}'. "
                            "Use only letters, digits, dot, underscore, or dash."
                        ),
                        template=template_name,
                    )
                )

            src = mount["src"]
            if src and src.lower().startswith("javascript:"):
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="islands",
                        message=(
                            f"Island '{name}' uses unsafe data-island-src '{src}'. "
                            "Use an http(s) or relative URL."
                        ),
                        template=template_name,
                    )
                )

            primitive_name = mount["primitive"] or name
            required = _ISLAND_PRIMITIVE_REQUIRED_KEYS.get(primitive_name)
            if required and mount["props_raw"] is None:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="islands",
                        message=(
                            f"Island '{name}' primitive '{primitive_name}' must define "
                            "data-island-props with required keys: "
                            f"{', '.join(sorted(required))}."
                        ),
                        template=template_name,
                    )
                )
    return issues

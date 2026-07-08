"""Kida 0.9 static-analysis contract checks."""

import logging
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, cast

from kida import Environment
from kida.analysis import (
    BlockAnalyzer,
    audit_escaping,
    check_context_contract,
    extract_literal_attributes,
    lint_privacy,
)

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida.analysis.context_contracts import SupportsContextAnalysis

_SKIPPED_TEMPLATE_PREFIXES = ("chirp/", "chirpui/")
_ROUTE_HX_ATTRS = frozenset({"hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete"})
_CONTEXT_CONTRACTS_KEY = "template_context_contracts"
_HIGH_SIGNAL_PRIVACY_TERMS = frozenset(
    {"api_key", "apikey", "authorization", "csrf", "password", "private", "secret", "token"}
)
_INTENTIONAL_RENDERED_SECURITY_HELPERS = frozenset({"csrf_token"})


def _user_templates(
    kida_env: Environment,
    template_sources: dict[str, str],
) -> Iterable[tuple[str, Any]]:
    for template_name in sorted(template_sources):
        if template_name.startswith(_SKIPPED_TEMPLATE_PREFIXES):
            continue
        try:
            yield template_name, kida_env.get_template(template_name)
        except Exception:
            logging.getLogger("chirp.contracts").debug(
                "Kida analysis skipped unloadable template %s",
                template_name,
                exc_info=True,
            )


def _location_details(
    *,
    code: str | None = None,
    lineno: int | None = None,
    col_offset: int | None = None,
    suggestion: str | None = None,
) -> str | None:
    parts: list[str] = []
    if code:
        parts.append(code)
    if lineno is not None:
        location = f"line {lineno}"
        if col_offset is not None:
            location += f", column {col_offset}"
        parts.append(location)
    if suggestion:
        parts.append(f"Suggestion: {suggestion}")
    return ". ".join(parts) if parts else None


def _is_static_literal(value: object) -> bool:
    return isinstance(value, str) and bool(
        value and "{{" not in value and "{%" not in value and "~" not in value
    )


def _static_literal_value(value: object) -> str | None:
    return value if _is_static_literal(value) and isinstance(value, str) else None


def _is_static_route_value(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(
        _is_static_literal(value)
        and not value.startswith(("#", "javascript:"))
        and "://" not in value
    )


def collect_literal_attributes(
    kida_env: Environment,
    template_sources: dict[str, str],
) -> dict[str, tuple[Any, ...]]:
    """Collect Kida literal attributes once for contract rules that need them."""
    attrs_by_template: dict[str, tuple[Any, ...]] = {}
    for template_name, template in _user_templates(kida_env, template_sources):
        attrs_by_template[template_name] = tuple(
            extract_literal_attributes(
                template,
                names=("id", "href", "src", "action"),
                prefixes=("hx-", "data-island"),
            )
        )
    return attrs_by_template


def literal_route_targets(attrs: Iterable[Any]) -> list[tuple[str, str, str | None]]:
    """Extract static hx-* route targets from Kida literal attributes."""
    targets: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for attr in attrs:
        name = getattr(attr, "name", "")
        value = _static_literal_value(getattr(attr, "value", None))
        if (
            not isinstance(name, str)
            or value is None
            or name not in _ROUTE_HX_ATTRS
            or not _is_static_route_value(value)
        ):
            continue
        target = (name, value, None)
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def literal_static_ids(attrs: Iterable[Any]) -> set[str]:
    """Extract static id= values from Kida literal attributes."""
    return {
        value.strip()
        for attr in attrs
        if getattr(attr, "name", "") == "id"
        for value in (_static_literal_value(getattr(attr, "value", None)),)
        if value is not None
    }


def literal_hx_target_selectors(attrs: Iterable[Any]) -> list[str]:
    """Extract static hx-target values from Kida literal attributes."""
    selectors: list[str] = []
    seen: set[str] = set()
    for attr in attrs:
        if getattr(attr, "name", "") != "hx-target":
            continue
        value = _static_literal_value(getattr(attr, "value", None))
        if value is None:
            continue
        selector = value.strip()
        if selector and selector not in seen:
            seen.add(selector)
            selectors.append(selector)
    return selectors


def literal_href_references(attrs: Iterable[Any]) -> set[str]:
    """Extract static href= route references from Kida literal attributes."""
    hrefs: set[str] = set()
    for attr in attrs:
        if getattr(attr, "name", "") != "href":
            continue
        value = _static_literal_value(getattr(attr, "value", None))
        if not _is_static_route_value(value) or value is None or not value.startswith("/"):
            continue
        base = value.split("?")[0].split("#")[0]
        if base:
            hrefs.add(base)
    return hrefs


def literal_htmx_partial_sources(attrs: Iterable[Any]) -> list[str]:
    """Extract static <htmx-partial src=...> route references from literal attributes."""
    urls: list[str] = []
    seen: set[str] = set()
    for attr in attrs:
        if getattr(attr, "tag", "").lower() != "htmx-partial":
            continue
        if getattr(attr, "name", "") != "src":
            continue
        value = _static_literal_value(getattr(attr, "value", None))
        if not _is_static_route_value(value) or value is None or not value.startswith("/"):
            continue
        path = value
        for sep in ("?", "#"):
            if sep in path:
                path = path.split(sep, 1)[0]
        if path and path not in seen:
            seen.add(path)
            urls.append(path)
    return urls


def check_component_calls(
    kida_env: Environment,
    template_sources: dict[str, str],
) -> tuple[list[ContractIssue], int]:
    """Validate local Kida component calls and literal argument types."""
    analyzer = BlockAnalyzer()
    issues: list[ContractIssue] = []

    for template_name, template in _user_templates(kida_env, template_sources):
        ast = getattr(template, "_optimized_ast", None)
        if ast is None:
            continue
        for issue in analyzer.validate_calls(ast):
            problems: list[str] = []
            if issue.unknown_params:
                problems.append(f"unknown parameter(s): {', '.join(issue.unknown_params)}")
            if issue.missing_required:
                problems.append(
                    f"missing required parameter(s): {', '.join(issue.missing_required)}"
                )
            if issue.duplicate_params:
                problems.append(f"duplicate parameter(s): {', '.join(issue.duplicate_params)}")
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="component",
                    message=(
                        f"Component call '{issue.def_name}' in template '{template_name}' "
                        f"has {', '.join(problems)}."
                    ),
                    template=template_name,
                    details=_location_details(lineno=issue.lineno, col_offset=issue.col_offset),
                )
            )
        issues.extend(
            ContractIssue(
                severity=Severity.ERROR,
                category="component",
                message=(
                    f"Component call '{mismatch.def_name}' in template '{template_name}' "
                    f"passes {mismatch.actual_type} for parameter '{mismatch.param_name}', "
                    f"but the definition expects {mismatch.expected}."
                ),
                template=template_name,
                details=_location_details(
                    lineno=mismatch.lineno,
                    col_offset=mismatch.col_offset,
                ),
            )
            for mismatch in analyzer.validate_call_types(ast)
        )

    return issues, len(issues)


def _normalize_context_spec(spec: Any) -> tuple[Any, Any, Any, bool] | None:
    if isinstance(spec, Mapping) and (
        "provided" in spec or "optional" in spec or "globals" in spec or "check_extra" in spec
    ):
        provided = spec.get("provided", ())
        optional = spec.get("optional")
        globals_ = spec.get("globals")
        check_extra = bool(spec.get("check_extra", False))
        return provided, optional, globals_, check_extra
    return spec, None, None, False


def check_template_context_contracts(
    kida_env: Environment,
    template_sources: dict[str, str],
    extras: Mapping[str, Any],
) -> list[ContractIssue]:
    """Validate opt-in dotted template context contracts with Kida."""
    raw_contracts = extras.get(_CONTEXT_CONTRACTS_KEY)
    if raw_contracts is None:
        return []
    if not isinstance(raw_contracts, Mapping):
        return [
            ContractIssue(
                severity=Severity.ERROR,
                category="template_context",
                message=(
                    f"{_CONTEXT_CONTRACTS_KEY!r} contract data must map template names "
                    "to provided context paths or contract spec dictionaries."
                ),
            )
        ]

    env_globals = set(kida_env.globals) if hasattr(kida_env, "globals") else set()
    issues: list[ContractIssue] = []
    for template_name, spec in raw_contracts.items():
        if not isinstance(template_name, str) or template_name not in template_sources:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="template_context",
                    message=f"Context contract references unknown template {template_name!r}.",
                    template=template_name if isinstance(template_name, str) else None,
                )
            )
            continue
        normalized = _normalize_context_spec(spec)
        if normalized is None:
            continue
        provided, optional, globals_, check_extra = normalized
        try:
            template = kida_env.get_template(template_name)
            merged_globals = env_globals | set(globals_ or ())
            # Kida's protocol currently models ``name`` as writable, while its
            # own immutable Template exposes it read-only. The remaining
            # analysis members are the exact runtime contract used below.
            analysis_template = cast("SupportsContextAnalysis", template)
            for issue in check_context_contract(
                analysis_template,
                provided,
                optional=optional,
                globals=merged_globals,
                check_extra=check_extra,
            ):
                severity = Severity.ERROR if issue.severity == "error" else Severity.WARNING
                issues.append(
                    ContractIssue(
                        severity=severity,
                        category="template_context",
                        message=issue.message,
                        template=template_name,
                        details=_location_details(
                            code=issue.code,
                            lineno=issue.lineno,
                            col_offset=issue.col_offset,
                            suggestion=issue.suggestion,
                        ),
                    )
                )
        except Exception as exc:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="template_context",
                    message=f"Context contract for template '{template_name}' could not run: {exc}",
                    template=template_name,
                )
            )
    return issues


def check_template_escape_audit(
    kida_env: Environment,
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Surface Kida trusted-markup findings without failing startup."""
    issues: list[ContractIssue] = []
    for template_name, template in _user_templates(kida_env, template_sources):
        for finding in audit_escaping(template):
            if finding.severity != "warning":
                continue
            expression = f" Expression: {finding.expression}." if finding.expression else ""
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="template_escape",
                    message=f"{finding.message}{expression}",
                    template=template_name,
                    details=_location_details(
                        code=finding.code,
                        lineno=finding.lineno,
                        col_offset=finding.col_offset,
                        suggestion=finding.suggestion,
                    ),
                )
            )
    return issues


def check_template_privacy(
    kida_env: Environment,
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Surface Kida privacy lint findings as warning-level contract diagnostics."""
    issues: list[ContractIssue] = []
    for template_name, template in _user_templates(kida_env, template_sources):
        issues.extend(
            ContractIssue(
                severity=Severity.WARNING,
                category="template_privacy",
                message=finding.message,
                template=template_name,
                details=_location_details(
                    code=finding.code,
                    lineno=finding.lineno,
                    col_offset=finding.col_offset,
                    suggestion=finding.suggestion,
                ),
            )
            for finding in lint_privacy(template)
            if _should_surface_privacy_finding(finding)
        )
    return issues


def _should_surface_privacy_finding(finding: Any) -> bool:
    if getattr(finding, "code", None) != "K-PRI-001":
        return True
    path = getattr(finding, "path", None)
    if not isinstance(path, str):
        return False
    lower = path.lower()
    if lower in _INTENTIONAL_RENDERED_SECURITY_HELPERS or lower.endswith("_field"):
        return False
    parts = set(re.split(r"[._:-]+", lower))
    return any(term in parts or term in lower for term in _HIGH_SIGNAL_PRIVACY_TERMS)

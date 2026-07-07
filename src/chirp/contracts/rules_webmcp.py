"""Startup contracts for experimental declarative WebMCP forms."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from chirp.contracts.rules_forms import extract_template_block_source
from chirp.contracts.types import ContractIssue, Severity
from chirp.webmcp import WebMCPForm

_FORM_TAG = re.compile(r"<form\b[^>]*>", re.IGNORECASE | re.DOTALL)
_FORM_HELPER = re.compile(r"webmcp_form_attrs\(\s*[\"']([^\"']+)[\"']\s*\)", re.IGNORECASE)
_CONTROL_HELPER = re.compile(
    r"webmcp_control_attrs\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']([^\"']+)[\"']\s*\)",
    re.IGNORECASE,
)
_CONTROL_TAG = re.compile(r"<(?:input|select|textarea)\b[^>]*>", re.IGNORECASE | re.DOTALL)
_MANAGED_LITERAL_CONTROL_ATTRIBUTE = re.compile(
    r"\b(?:type|name|required|value|min|max|step|minlength|maxlength|pattern)\b"
    r"(?:\s*=)?",
    re.IGNORECASE,
)
_RAW_TOOL_NAME = re.compile(r"\btoolname\s*=", re.IGNORECASE)
_RAW_GENERATED_ATTRIBUTE = re.compile(
    r"\b(?:tooldescription|toolparamdescription|toolautosubmit)\b", re.IGNORECASE
)
_ACTION = re.compile(r"\baction\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_METHOD = re.compile(r"\bmethod\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_SUBMIT = re.compile(
    r"<(?:button\b[^>]*\btype\s*=\s*[\"']submit[\"']|input\b[^>]*\btype\s*=\s*[\"']submit[\"'])",
    re.IGNORECASE | re.DOTALL,
)
_CSRF = re.compile(r"csrf_field\s*\(|name\s*=\s*[\"']_?csrf_token[\"']", re.IGNORECASE)
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _issue(
    message: str,
    *,
    route: str | None,
    template: str | None,
    details: str | None = None,
) -> ContractIssue:
    return ContractIssue(
        severity=Severity.ERROR,
        category="webmcp",
        message=message,
        route=route,
        template=template,
        details=details,
    )


def _context(tool: str, route: str, template: str, block: str | None) -> str:
    location = f"template {template!r}"
    if block:
        location += f" block {block!r}"
    return f"WebMCP operation {tool!r} on route {route!r}, {location}"


def check_webmcp_contracts(
    router: Any,
    template_sources: Mapping[str, str],
    middleware: Iterable[Any],
    compile_diagnostics: Iterable[Any],
    valid_tools: Iterable[str],
) -> list[ContractIssue]:
    """Validate opted-in projections and raw agent-visible markup."""
    issues: list[ContractIssue] = []
    valid_tool_set = frozenset(valid_tools)
    declared_tools: set[str] = set()
    declared_templates: set[str] = set()
    invalid_templates: set[str] = set()
    csrf_enabled = any(item.__class__.__name__ == "CSRFMiddleware" for item in middleware)

    for diagnostic in compile_diagnostics:
        tool = str(getattr(diagnostic, "tool_name", "<missing>"))
        route = str(getattr(diagnostic, "route", "<unknown>"))
        template = getattr(diagnostic, "template", None)
        block = getattr(diagnostic, "block", None)
        message = str(getattr(diagnostic, "message", "Invalid WebMCP projection."))
        if isinstance(template, str):
            invalid_templates.add(template)
        issues.append(
            _issue(
                f"{_context(tool, route, template or '<unknown>', block)} is invalid: {message}",
                route=route,
                template=template,
                details="Fix the FormContract projection before exposing it to browser agents.",
            )
        )

    for route in getattr(router, "routes", ()):
        route_contract = getattr(route.handler, "_chirp_contract", None)
        form_contract = getattr(route_contract, "form", None)
        declaration = getattr(form_contract, "webmcp", None)
        if not isinstance(declaration, WebMCPForm):
            continue
        tool = declaration.tool_name or "<missing>"
        declared_tools.add(tool)
        template = str(getattr(form_contract, "template", ""))
        declared_templates.add(template)
        block = getattr(form_contract, "block", None)
        context = _context(tool, route.path, template, block)
        if tool not in valid_tool_set:
            continue
        if not block:
            issues.append(
                _issue(
                    f"{context} must name the form block explicitly.",
                    route=route.path,
                    template=template,
                    details="Set FormContract(..., block='form_block') so checks inspect one form.",
                )
            )
            continue
        source = template_sources.get(template)
        if source is None:
            issues.append(
                _issue(
                    f"{context} references a missing template.",
                    route=route.path,
                    template=template,
                    details=f"Create {template!r} or correct FormContract.template.",
                )
            )
            continue
        block_source = extract_template_block_source(source, block)
        if block_source is None:
            issues.append(
                _issue(
                    f"{context} references a missing named block.",
                    route=route.path,
                    template=template,
                    details=f"Add {{% block {block} %}} or correct FormContract.block.",
                )
            )
            continue

        matching_forms = [
            tag for tag in _FORM_TAG.findall(block_source) if tool in _FORM_HELPER.findall(tag)
        ]
        helper_tools = _FORM_HELPER.findall(block_source)
        if len(matching_forms) != 1:
            issues.append(
                _issue(
                    f"{context} must render exactly one real <form> with "
                    f"webmcp_form_attrs({tool!r}); found {len(matching_forms)}.",
                    route=route.path,
                    template=template,
                    details=(
                        f"Observed helper operation IDs: {', '.join(helper_tools) or '(none)'}. "
                        "Keep the ordinary form and add the compiled helper to its opening tag."
                    ),
                )
            )
        else:
            form_tag = matching_forms[0]
            action = _ACTION.search(form_tag)
            method = _METHOD.search(form_tag)
            methods = frozenset(str(value).upper() for value in route.methods)
            if action is None or not action.group(1).strip():
                issues.append(
                    _issue(
                        f"{context} has no literal fallback form action.",
                        route=route.path,
                        template=template,
                        details=f"Set action={route.path!r}; browser agents and humans submit the same route.",
                    )
                )
            elif "{{" not in action.group(1) and action.group(1) != route.path:
                issues.append(
                    _issue(
                        f"{context} fallback form action {action.group(1)!r} does not match "
                        f"route path {route.path!r}.",
                        route=route.path,
                        template=template,
                        details="Point the native form action at the same registered route.",
                    )
                )
            observed_method = method.group(1).upper() if method else "GET"
            if observed_method not in methods:
                issues.append(
                    _issue(
                        f"{context} fallback form method {observed_method!r} does not match "
                        f"route methods {', '.join(sorted(methods))}.",
                        route=route.path,
                        template=template,
                        details="Correct the native method attribute; WebMCP does not replace submission.",
                    )
                )

        if not _SUBMIT.search(block_source):
            issues.append(
                _issue(
                    f"{context} has no native submit control for human fallback.",
                    route=route.path,
                    template=template,
                    details='Add <button type="submit"> so unsupported browsers remain complete.',
                )
            )

        try:
            datacls = cast(type, getattr(form_contract, "datacls", None))
            expected_fields = {field.name for field in dataclasses.fields(datacls)}
        except TypeError:
            expected_fields = set()
        observed_pairs = _CONTROL_HELPER.findall(block_source)
        observed_fields = {field for helper_tool, field in observed_pairs if helper_tool == tool}
        issues.extend(
            _issue(
                f"{context} does not project form control {field_name!r}.",
                route=route.path,
                template=template,
                details=f"Render webmcp_control_attrs({tool!r}, {field_name!r}) on that control.",
            )
            for field_name in sorted(expected_fields - observed_fields)
        )
        for helper_tool, field_name in observed_pairs:
            if helper_tool != tool or field_name not in expected_fields:
                issues.append(
                    _issue(
                        f"{context} contains mismatched control helper for operation "
                        f"{helper_tool!r}, field {field_name!r}.",
                        route=route.path,
                        template=template,
                        details="Use the FormContract operation ID and one of its dataclass fields.",
                    )
                )
        for control_tag in _CONTROL_TAG.findall(block_source):
            if not _CONTROL_HELPER.search(control_tag):
                continue
            source_without_helper = _CONTROL_HELPER.sub("", control_tag)
            managed = _MANAGED_LITERAL_CONTROL_ATTRIBUTE.search(source_without_helper)
            if managed:
                issues.append(
                    _issue(
                        f"{context} mixes compiled control metadata with literal "
                        f"{managed.group(0).rstrip('= ').lower()!r} on the same control.",
                        route=route.path,
                        template=template,
                        details=(
                            "Remove the duplicate native/tool attribute; WebMCP control helpers "
                            "derive names, descriptions, requiredness, constraints, and defaults "
                            "from the server FormContract."
                        ),
                    )
                )

        if _RAW_GENERATED_ATTRIBUTE.search(block_source) or _RAW_TOOL_NAME.search(block_source):
            issues.append(
                _issue(
                    f"{context} mixes raw WebMCP attributes with compiled helpers.",
                    route=route.path,
                    template=template,
                    details="Remove raw tool* attributes; descriptions and policy come from FormContract.",
                )
            )

        methods = frozenset(str(value).upper() for value in route.methods)
        if methods & _MUTATING_METHODS:
            if declaration.autosubmit:
                # Normally supplied by compiler diagnostics; retain static defense in depth.
                issues.append(
                    _issue(
                        f"{context} cannot auto-submit a mutation.",
                        route=route.path,
                        template=template,
                        details="Set autosubmit=False so the browser requires human confirmation.",
                    )
                )
            if not csrf_enabled:
                issues.append(
                    _issue(
                        f"{context} exposes a mutation without CSRFMiddleware.",
                        route=route.path,
                        template=template,
                        details="Register SessionMiddleware then CSRFMiddleware before serving the tool.",
                    )
                )
            elif not _CSRF.search(block_source):
                issues.append(
                    _issue(
                        f"{context} omits the CSRF field from its fallback form.",
                        route=route.path,
                        template=template,
                        details="Render {{ csrf_field() }} inside the same real form.",
                    )
                )

    for template, source in template_sources.items():
        raw = bool(_RAW_TOOL_NAME.search(source))
        if template not in invalid_templates:
            issues.extend(
                _issue(
                    f"Template {template!r} exposes undeclared WebMCP operation {tool!r}.",
                    route=None,
                    template=template,
                    details="Add WebMCPForm to the matching FormContract or remove the helper.",
                )
                for tool in _FORM_HELPER.findall(source)
                if tool not in declared_tools
            )
        if raw and template not in declared_templates:
            issues.append(
                _issue(
                    f"Template {template!r} contains raw toolname markup without verified projection metadata.",
                    route=None,
                    template=template,
                    details="Use FormContract(webmcp=WebMCPForm(...)) and compiled template helpers.",
                )
            )
    return issues

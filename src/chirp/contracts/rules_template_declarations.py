"""Validation for explicit dynamic template reachability declarations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app.hypermedia_program import HypermediaProgram, SourceOrigin


def _format_origin(origin: SourceOrigin) -> str:
    if origin.line is None:
        return origin.identifier
    return f"{origin.identifier}:{origin.line}"


def check_template_declarations(program: HypermediaProgram | None) -> list[ContractIssue]:
    """Return actionable errors for unknown declared templates and blocks."""
    if program is None:
        return []

    issues: list[ContractIssue] = []
    for declaration in program.template_declarations:
        origin = _format_origin(declaration.origin)
        template = program.template(declaration.template)
        if template is None:
            error_kind = "not compiled"
        elif template.load_error is not None:
            error_kind = template.load_error
        else:
            error_kind = None
        if error_kind is not None:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="template_declaration",
                    message=(
                        f"Declared template {declaration.template!r} from {origin} "
                        f"could not be loaded ({error_kind}). Fix the template name or loader."
                    ),
                    template=declaration.template,
                    details=f"Declaration origin: {origin}",
                )
            )
            continue

        available = program.block_names(declaration.template)
        for block in declaration.blocks:
            if block in available:
                continue
            available_text = ", ".join(sorted(available)) or "<none>"
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="template_declaration",
                    message=(
                        f"Declared block {block!r} does not exist in template "
                        f"{declaration.template!r} (declared at {origin}). "
                        f"Available blocks: {available_text}."
                    ),
                    template=declaration.template,
                    details=f"Declaration origin: {origin}",
                )
            )
    return issues

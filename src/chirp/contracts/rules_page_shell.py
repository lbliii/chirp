"""Page shell contract validation."""

from chirp.app.hypermedia_program import HypermediaProgram

from .types import ContractIssue, Severity


def check_page_shell_contracts(
    program: HypermediaProgram | None,
) -> list[ContractIssue]:
    """Validate required fragment blocks across page templates.

    Page shell contracts describe which fragment blocks leaf page templates
    must expose for registered shell targets like ``#main`` and ``#page-root``.
    """
    issues: list[ContractIssue] = []
    if program is None:
        return issues
    required_targets = tuple(target for target in program.targets if target.required)
    page_templates = program.page_leaf_templates
    if not page_templates or not required_targets:
        return issues

    for template in page_templates:
        if template.load_error is not None:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="page_shell",
                    message=(
                        f"Page template '{template.name}' could not be loaded while validating "
                        "the page shell contract."
                    ),
                    template=template.name,
                    details=template.load_error,
                )
            )
            continue

        transitions = program.target_block_transitions(template_name=template.name)
        resolved_by_target = {edge.source_id: edge.resolved for edge in transitions}
        missing_blocks = sorted(
            {
                target.fragment_block
                for target in required_targets
                if not resolved_by_target.get(target.id, False)
            }
        )
        if not missing_blocks:
            continue

        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="page_shell",
                message=(
                    f"Page template '{template.name}' does not satisfy the registered page shell "
                    f"contract. Missing required block(s): {', '.join(missing_blocks)}."
                ),
                template=template.name,
                details=(
                    "Register a different page shell contract for this app, or make the template "
                    "inherit/provide the required block boundaries."
                ),
            )
        )

    return issues

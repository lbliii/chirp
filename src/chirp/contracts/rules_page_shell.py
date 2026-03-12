"""Page shell contract validation."""

from kida import Environment

from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .types import ContractIssue, Severity


def check_page_shell_contracts(
    page_templates: set[str],
    fragment_target_registry: FragmentTargetRegistry,
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Validate required fragment blocks across page templates.

    Page shell contracts describe which fragment blocks leaf page templates
    must expose for registered shell targets like ``#main`` and ``#page-root``.
    """
    issues: list[ContractIssue] = []
    required_blocks = fragment_target_registry.required_fragment_blocks
    if not page_templates or not required_blocks or kida_env is None:
        return issues

    for template_name in sorted(page_templates):
        try:
            template = kida_env.get_template(template_name)
            blocks = template.block_metadata()
        except Exception as exc:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="page_shell",
                    message=(
                        f"Page template '{template_name}' could not be loaded while validating "
                        "the page shell contract."
                    ),
                    template=template_name,
                    details=str(exc),
                )
            )
            continue

        missing_blocks = sorted(block for block in required_blocks if block not in blocks)
        if not missing_blocks:
            continue

        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="page_shell",
                message=(
                    f"Page template '{template_name}' does not satisfy the registered page shell "
                    f"contract. Missing required block(s): {', '.join(missing_blocks)}."
                ),
                template=template_name,
                details=(
                    "Register a different page shell contract for this app, or make the template "
                    "inherit/provide the required block boundaries."
                ),
            )
        )

    return issues

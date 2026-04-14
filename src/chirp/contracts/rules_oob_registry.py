"""OOB registry / layout consistency check.

Warns at startup when the OOB registry contains blocks (e.g. shell_actions_oob)
that no layout template defines.  Without the matching ``{% region %}`` or
``{% block %}``, the registered region is inert — OOB swaps silently fail,
and the developer only discovers the mismatch via runtime errors.
"""

from kida import Environment

from chirp.templating.oob_registry import OOBRegistry

from .types import ContractIssue, Severity


def check_oob_registry_coverage(
    oob_registry: OOBRegistry | None,
    layout_templates: list[str],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Warn when registered OOB blocks are absent from all layout templates.

    For each block in the OOB registry, checks whether at least one layout
    template defines that block.  Emits a WARNING for each orphaned
    registration so the developer can add the missing ``{% region %}`` or
    remove the registration.
    """
    if oob_registry is None or kida_env is None or not layout_templates:
        return []

    registered = set(oob_registry.registered_blocks)
    if not registered:
        return []

    # Collect blocks defined across all layout templates
    defined_blocks: set[str] = set()
    for template_name in layout_templates:
        try:
            tmpl = kida_env.get_template(template_name)
            meta = tmpl.template_metadata()
        except Exception:
            continue
        blocks = getattr(meta, "blocks", None)
        if blocks is not None:
            defined_blocks.update(blocks)

    orphaned = sorted(registered - defined_blocks)
    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="oob_registry",
            message=(
                f"OOB region '{block}' is registered in the OOB registry "
                f"(target: '{oob_registry.resolve_target(block)}') but no layout "
                f"template defines a matching block. OOB swaps for this region "
                f"will be skipped. Add {{% region {block} %}} to your layout, "
                f"or remove the registration."
            ),
        )
        for block in orphaned
    ]

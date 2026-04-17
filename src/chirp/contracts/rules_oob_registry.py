"""OOB registry / layout consistency check.

Fails loud at startup when the OOB registry contains blocks (e.g.
shell_actions_oob) that no layout template defines.  Without the matching
``{% region %}`` or ``{% block %}``, the registered region is inert — OOB
swaps would silently fail at render time, so reaching ``app.check()`` with
an orphaned registration is almost always a bug.

Severity tiering:
- ``optional=False`` (default): ERROR. Render-time pre-check would raise
  ``BlockNotFoundError`` on a request hitting this layout, so flagging at
  startup is the earlier, cheaper signal.
- ``optional=True``: WARNING. Apps that intentionally register regions for
  some-but-not-all layouts opt in; the render path silently skips them.

Apps that need the pre-0.5.0 behavior can demote globally with
``app.override_contract_severity("oob_registry", Severity.WARNING)``.
"""

from kida import Environment

from chirp.templating.oob_registry import OOBRegistry

from .types import ContractIssue, Severity


def check_oob_registry_coverage(
    oob_registry: OOBRegistry | None,
    layout_templates: list[str],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Emit ERROR/WARNING issues for OOB blocks absent from all layouts.

    For each block in the OOB registry, checks whether at least one layout
    template defines that block. Non-optional orphans emit ERROR (render
    would raise); optional orphans emit WARNING (render silently skips).
    """
    if oob_registry is None or kida_env is None or not layout_templates:
        return []

    registered = set(oob_registry.registered_blocks)
    if not registered:
        return []

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
    issues: list[ContractIssue] = []
    for block in orphaned:
        config = oob_registry.get(block)
        is_optional = config is not None and config.optional
        severity = Severity.WARNING if is_optional else Severity.ERROR
        if is_optional:
            remedy = (
                "This region is marked optional=True so OOB swaps for it are "
                "silently skipped at render time; remove the registration if "
                "it is no longer needed."
            )
        else:
            remedy = (
                f"Add {{% region {block} %}} to your layout, remove the "
                "registration, or pass optional=True to register_oob_region "
                "if layouts legitimately omit this block."
            )
        issues.append(
            ContractIssue(
                severity=severity,
                category="oob_registry",
                message=(
                    f"OOB region '{block}' is registered in the OOB registry "
                    f"(target: '{oob_registry.resolve_target(block)}') but no "
                    f"layout template defines a matching block. {remedy}"
                ),
            )
        )
    return issues

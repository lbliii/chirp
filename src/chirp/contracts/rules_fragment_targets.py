"""Fragment target registry orphan check.

Fails loud at startup when the fragment target registry contains entries
whose ``fragment_block`` is not defined by any page leaf template. Such
registrations are inert: boosted requests hitting that HX-Target resolve
to a block that does not exist, producing a runtime ``BlockNotFoundError``
(for required targets) or silently falling back to full-page composition
(for optional targets).

Relation to sibling checks:
- ``check_page_shell_contracts`` iterates each page template and reports
  missing *required* blocks per-template. High per-page fidelity but
  noisy when a registration is simply dead.
- This check iterates each *registration* and reports orphans once per
  target — a single high-signal issue per registry typo. It is also the
  only check covering ``required=False`` targets.

Severity tiering:
- ``required=True`` (contract-required or ad-hoc required): ERROR.
  Render-time would raise ``BlockNotFoundError`` on any boosted request
  matching the target id.
- ``required=False``: WARNING. Silent render fallback keeps requests
  working, but the registration is almost certainly a typo or stale.

Apps can demote globally via
``app.override_contract_severity("fragment_target_orphan", Severity.WARNING)``.
"""

from kida import Environment

from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .types import ContractIssue, Severity


def check_fragment_target_orphans(
    fragment_target_registry: FragmentTargetRegistry,
    page_templates: set[str],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Emit ERROR/WARNING issues for targets whose block no template defines."""
    if kida_env is None or not page_templates:
        return []

    registered = fragment_target_registry.registered_targets
    if not registered:
        return []

    defined_blocks: set[str] = set()
    issues: list[ContractIssue] = []
    for template_name in page_templates:
        try:
            template = kida_env.get_template(template_name)
            blocks = template.block_metadata()
        except Exception as exc:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="fragment_target_scan",
                    message=(
                        f"Could not inspect template '{template_name}' while checking "
                        f"fragment target registrations: {type(exc).__name__}: {exc}"
                    ),
                    template=template_name,
                )
            )
            continue
        if blocks is not None:
            defined_blocks.update(blocks)

    for target_id in sorted(registered):
        config = fragment_target_registry.get(target_id)
        if config is None:
            continue
        if config.fragment_block in defined_blocks:
            continue
        severity = Severity.ERROR if config.required else Severity.WARNING
        contract_label = f" (contract '{config.contract_name}')" if config.contract_name else ""
        if config.required:
            remedy = (
                "Define the block in a page template, fix the fragment_block "
                "argument, or drop required=True if the target is legitimately "
                "optional."
            )
        else:
            remedy = (
                "Define the block in a page template or remove the registration "
                "if it is no longer needed."
            )
        issues.append(
            ContractIssue(
                severity=severity,
                category="fragment_target_orphan",
                message=(
                    f"Fragment target '#{target_id}'{contract_label} maps to block "
                    f"'{config.fragment_block}' but no page template defines that block. "
                    f"{remedy}"
                ),
            )
        )
    return issues

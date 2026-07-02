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

from chirp.app.hypermedia_program import HypermediaProgram

from .types import ContractIssue, Severity


def check_fragment_target_orphans(
    program: HypermediaProgram | None,
) -> list[ContractIssue]:
    """Emit ERROR/WARNING issues for targets whose block no template defines."""
    if program is None or not program.page_leaf_templates:
        return []
    if not program.targets:
        return []

    issues = [
        ContractIssue(
            severity=Severity.ERROR,
            category="fragment_target_scan",
            message=(
                f"Could not inspect template '{template.name}' while checking "
                f"fragment target registrations: {template.load_error}"
            ),
            template=template.name,
        )
        for template in program.page_leaf_templates
        if template.load_error is not None
    ]

    for target in program.targets:
        transitions = program.target_block_transitions(target_id=target.target_id)
        if any(edge.resolved for edge in transitions):
            continue
        severity = Severity.ERROR if target.required else Severity.WARNING
        contract_label = f" (contract '{target.contract_name}')" if target.contract_name else ""
        if target.required:
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
                    f"Fragment target '#{target.target_id}'{contract_label} maps to block "
                    f"'{target.fragment_block}' but no page template defines that block. "
                    f"{remedy}"
                ),
            )
        )
    return issues

"""OOB swap target cross-reference checks.

Warns when hx-swap-oob targets an ID not found in any template.
"""

import re

from .types import ContractIssue, Severity

# Match: <tag ... hx-swap-oob="..." ... id="..." ...>
# and:   <tag ... id="..." ... hx-swap-oob="..." ...>
_OOB_WITH_ID = re.compile(
    r"<[^>]+\bhx-swap-oob\s*=\s*[\"'][^\"']*[\"'][^>]*\bid\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_ID_WITH_OOB = re.compile(
    r"<[^>]+\bid\s*=\s*[\"']([^\"']+)[\"'][^>]*\bhx-swap-oob\s*=\s*[\"'][^\"']*[\"']",
    re.IGNORECASE | re.DOTALL,
)


def check_oob_targets(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> list[ContractIssue]:
    """Warn when hx-swap-oob targets an ID not found in any template.

    Scans template sources for elements with both ``hx-swap-oob`` and
    ``id`` attributes, then checks if that ID exists anywhere across
    all templates (via the pre-built ``all_ids`` set).

    Only catches statically-analyzable targets. Dynamic IDs (Kida
    expressions) are excluded by design.
    """
    issues: list[ContractIssue] = []

    for template_name, source in template_sources.items():
        oob_ids: set[str] = set()

        for pattern in (_OOB_WITH_ID, _ID_WITH_OOB):
            for match in pattern.finditer(source):
                id_val = match.group(1).strip()
                if id_val and "{{" not in id_val and "{%" not in id_val:
                    oob_ids.add(id_val)

        missing = sorted(oob_ids - all_ids)
        issues.extend(
            ContractIssue(
                severity=Severity.WARNING,
                category="oob_target",
                message=(
                    f'hx-swap-oob element targets id="{oob_id}" but no '
                    "element with that ID was found in any template. "
                    "The OOB swap will silently fail."
                ),
                template=template_name,
            )
            for oob_id in missing
        )

    return issues

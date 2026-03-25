"""Contract rules for Vary header correctness.

Warns when templates manually branch on ``is_fragment`` / ``HX-Request``
outside of Chirp's ``Page`` return type, which auto-sets ``Vary: HX-Request``.
Manual branching without ``Vary`` causes HTTP caches to serve the wrong
response variant.
"""

import re

from .types import ContractIssue, Severity

# Patterns that indicate manual fragment branching in templates
_IS_FRAGMENT_PATTERN = re.compile(
    r"\{%-?\s*if\s+.*?\bis_fragment\b",
)
_HX_REQUEST_PATTERN = re.compile(
    r"\{%-?\s*if\s+.*?\brequest\.htmx\b|\brequest\.is_fragment\b",
)


def check_vary_coverage(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Warn when templates branch on htmx request state.

    Chirp's ``Page`` return type sets ``Vary: HX-Request`` automatically.
    If a template manually checks ``is_fragment`` (via ``{% if %}`` blocks),
    it likely needs the ``Page`` type or explicit ``Vary`` handling.
    """
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        if _IS_FRAGMENT_PATTERN.search(source) or _HX_REQUEST_PATTERN.search(source):
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="vary",
                    message=(
                        f"Template '{template_name}' branches on is_fragment / "
                        f"request.htmx. Use the Page return type (which auto-sets "
                        f"Vary: HX-Request) or manually set the Vary header to "
                        f"prevent HTTP caches from serving wrong response variants."
                    ),
                    template=template_name,
                )
            )
    return issues

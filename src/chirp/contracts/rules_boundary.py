"""Error boundary coverage check for OOB template blocks.

Scans template sources for blocks inside elements with ``hx-swap-oob``
attributes and suggests wrapping them in ``{% try %}...{% fallback %}``
for graceful error handling.

This only catches templates that *embed* ``hx-swap-oob`` in their source.
Templates used with ``Suspense`` don't contain ``hx-swap-oob`` — the OOB
wrappers are generated at render time by chirp's Suspense pipeline, which
already has its own per-block error handling (see ``suspense.py``).

Kida 0.4.0 introduced error boundaries — ``{% try %}`` blocks that catch
render errors and fall back to safe defaults.

This check emits INFO-level issues (not errors or warnings) since
server-side error handling already prevents page-level failures.
"""

import re

from .types import ContractIssue, Severity

_BLOCK_PATTERN = re.compile(
    r"""\{%-?\s*block\s+(?P<name>\w+)\s*-?%\}(?P<body>.*?)\{%-?\s*end(?:block)?(?:\s+\w+)?\s*-?%\}""",
    re.DOTALL | re.IGNORECASE,
)

_OOB_PATTERN = re.compile(
    r"""hx-swap-oob\s*=\s*["']""",
    re.IGNORECASE,
)

_TRY_PATTERN = re.compile(
    r"""\{%-?\s*try\b""",
    re.IGNORECASE,
)


def check_boundary_coverage(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Suggest error boundaries for blocks in OOB templates.

    Only inspects templates whose source contains ``hx-swap-oob`` attributes
    (explicit OOB swap targets).  Within those templates, blocks without
    ``{% try %}`` get an INFO issue.  Does not cover Suspense-rendered OOB
    (those wrappers are generated at render time, not in the source).
    """
    issues: list[ContractIssue] = []

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue

        if not _OOB_PATTERN.search(source):
            continue

        for m in _BLOCK_PATTERN.finditer(source):
            block_name = m.group("name")
            block_body = m.group("body")

            if _TRY_PATTERN.search(block_body):
                continue

            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="boundary",
                    message=(
                        f"Block '{block_name}' in OOB template lacks "
                        f"{{% try %}} error boundary — consider wrapping "
                        f"for graceful fallback."
                    ),
                    template=template_name,
                )
            )

    return issues

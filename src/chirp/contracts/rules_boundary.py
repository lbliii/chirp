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

**Scope limitations** — the check uses regex-based HTML parsing, so it:
- Only sees blocks in the literal template source (not inherited/included blocks)
- May miss OOB regions split across template conditionals
These are acceptable trade-offs for an INFO-level advisory check.
"""

import re

from .types import ContractIssue, Severity

_BLOCK_PATTERN = re.compile(
    r"""\{%-?\s*block\s+(?P<name>\w+)\s*-?%\}(?P<body>.*?)\{%-?\s*end(?:block)?(?:\s+\w+)?\s*-?%\}""",
    re.DOTALL | re.IGNORECASE,
)

# Matches the opening tag of an OOB element, capturing its tag name.
_OOB_OPEN_PATTERN = re.compile(
    r"""<(?P<tag>\w+)[^>]+hx-swap-oob\s*=\s*["']""",
    re.IGNORECASE,
)

_TRY_PATTERN = re.compile(
    r"""\{%-?\s*try\b""",
    re.IGNORECASE,
)


def _extract_oob_regions(source: str) -> list[str]:
    """Extract the inner content of each OOB element by tracking tag nesting.

    Limitations (regex-based HTML parsing):
    - Cannot see blocks inherited via ``{% extends %}`` or pulled in via
      ``{% include %}`` — only the literal source of each template is scanned.
    - HTML comments or template conditionals that split tags may confuse the
      nesting tracker, though this is rare in practice.
    """
    regions: list[str] = []
    for oob_open in _OOB_OPEN_PATTERN.finditer(source):
        tag = oob_open.group("tag")
        # Find the end of the opening tag
        gt_pos = source.find(">", oob_open.end())
        if gt_pos == -1:
            continue
        inner_start = gt_pos + 1
        # Track nesting to find the matching closing tag
        open_pat = re.compile(rf"<{tag}\b", re.IGNORECASE)
        close_pat = re.compile(rf"</{tag}\s*>", re.IGNORECASE)
        depth = 1
        pos = inner_start
        while depth > 0 and pos < len(source):
            next_open = open_pat.search(source, pos)
            next_close = close_pat.search(source, pos)
            if next_close is None:
                break
            if next_open and next_open.start() < next_close.start():
                depth += 1
                pos = next_open.end()
            else:
                depth -= 1
                if depth == 0:
                    regions.append(source[inner_start : next_close.start()])
                pos = next_close.end()
    return regions


def check_boundary_coverage(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Suggest error boundaries for blocks inside OOB elements.

    Only inspects blocks that are *inside* elements with ``hx-swap-oob``
    attributes (explicit OOB swap targets).  Blocks outside OOB regions in the
    same template are not flagged.  Does not cover Suspense-rendered OOB
    (those wrappers are generated at render time, not in the source).
    """
    issues: list[ContractIssue] = []

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue

        for oob_inner in _extract_oob_regions(source):
            for m in _BLOCK_PATTERN.finditer(oob_inner):
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

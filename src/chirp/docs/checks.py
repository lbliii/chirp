"""Contract checks for documentation integrity.

Registered by ``DocsPlugin`` when mounted.  Each check receives the
``ContractCheckSnapshot`` and appends issues to the ``CheckResult``.

Checks:
    - ``check_docs_parseable`` — all ``.md`` files in content_dir parse
    - ``check_docs_no_duplicate_slugs`` — no slug collisions
    - ``check_docs_cross_references`` — internal ``[text](slug)`` links resolve
    - ``check_docs_no_drafts_exposed`` — drafts excluded unless include_drafts
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app.state import ContractCheckSnapshot
    from chirp.contracts.types import CheckResult

_INTERNAL_LINK_RE = re.compile(r"\[([^\]]*)\]\((?!https?://|#|mailto:)([^)]+)\)")


def _get_collection(snapshot: ContractCheckSnapshot):
    """Read the live collection from the holder stored in extras."""
    holder = snapshot.extras.get("docs_holder")
    if holder is None:
        return None
    return holder.collection


def check_docs_parseable(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Verify all ``.md`` files in the content directory are parseable."""
    from chirp.docs.frontmatter import parse_file

    content_dir = snapshot.extras.get("docs_content_dir")
    if content_dir is None:
        return

    for md_path in sorted(content_dir.rglob("*.md")):
        try:
            parse_file(md_path, content_dir)
        except Exception as exc:
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="docs_parse",
                    message=f"Failed to parse {md_path.name}: {exc}",
                    details=str(md_path),
                )
            )


def check_docs_no_duplicate_slugs(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Detect duplicate slugs across markdown and autodoc pages."""
    collection = _get_collection(snapshot)
    if collection is None:
        return

    seen: dict[str, str] = {}
    for page in collection._pages:
        source_label = page.source.value
        if page.slug in seen:
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="docs_duplicate_slug",
                    message=(f"Duplicate slug '{page.slug}' ({seen[page.slug]} vs {source_label})"),
                )
            )
        else:
            seen[page.slug] = source_label


def check_docs_cross_references(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Verify internal markdown links resolve to existing slugs."""
    collection = _get_collection(snapshot)
    docs_prefix = snapshot.extras.get("docs_prefix", "/docs")
    if collection is None:
        return

    prefix_with_slash = docs_prefix.rstrip("/") + "/"

    for page in collection._pages:
        for match in _INTERNAL_LINK_RE.finditer(page.raw):
            target = match.group(2)

            # Skip anchors and absolute paths not under docs prefix
            if target.startswith("#"):
                continue
            if target.startswith("/") and not target.startswith(prefix_with_slash):
                continue

            # Skip file paths with extensions (images, downloads, etc.)
            final_segment = target.split("/")[-1].split("#")[0]
            if "." in final_segment:
                continue

            # Resolve the target to a slug
            if target.startswith(prefix_with_slash):
                slug = target[len(prefix_with_slash) :]
            elif target.startswith("/"):
                continue
            else:
                slug = target

            # Strip trailing slash and anchors
            slug = slug.rstrip("/").split("#")[0]
            if not slug:
                continue

            if slug not in collection:
                result.issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="docs_cross_ref",
                        message=(
                            f"Broken cross-reference in '{page.slug}': link to '{slug}' not found"
                        ),
                        details=f"Link text: {match.group(1)}",
                    )
                )


def check_docs_no_drafts_exposed(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Warn if draft pages are included in the live collection."""
    collection = _get_collection(snapshot)
    include_drafts = snapshot.extras.get("docs_include_drafts", False)
    if collection is None or include_drafts:
        return

    for page in collection._pages:
        if page.metadata.draft:
            result.issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="docs_draft_exposed",
                    message=f"Draft page '{page.slug}' is in the live collection",
                    details=str(page.source_path) if page.source_path else None,
                )
            )

"""Page-template-extends-registered-layout footgun detection.

When a page-leaf template uses ``{% extends "_layout.html" %}`` and
``_layout.html`` is registered as a layout in this page's chain, two things
break silently:

1. **Block overrides are dropped.** ``render_with_blocks`` only injects the
   page's rendered HTML into the layout's ``content`` slot — sibling block
   overrides like ``{% block page_scripts %}`` defined on the page never
   reach the layout. The page author wonders why their inline script tag
   doesn't show up; nothing in the console explains it.

2. **The layout structure renders twice.** kida's extends inheritance fills
   the layout structure during page render, then ``render_with_layouts``
   wraps that already-wrapped HTML in the same layout chain again — the
   ``<html>``/``<body>`` shell appears nested inside itself.

``check_unreachable_blocks`` covers the no-extends sibling-block case but
explicitly skips templates that use ``{% extends %}`` (see
``rules_unreachable_blocks.py``); this rule is the complementary check
targeting the extends-into-a-registered-layout case.

Detection is conservative: only fires when the extended target is in this
app's set of **registered** layout template names. Pages that extend a
non-layout kida partial (e.g. the ``_page_layout.html`` pattern in
``examples/standalone/oob_layout_chain/``) are intentionally allowed.
"""

from typing import Any

from kida import Environment

from .types import ContractIssue, Severity


def _registered_layout_names(layout_chains: list[Any]) -> set[str]:
    """Collect every layout template name registered in any page chain."""
    names: set[str] = set()
    for chain in layout_chains:
        for layout in getattr(chain, "layouts", ()):
            name = getattr(layout, "template_name", None)
            if name:
                names.add(name)
    return names


def check_page_extends_layout(
    page_leaf_templates: set[str],
    layout_chains: list[Any],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Flag page-leaf templates that ``{% extends %}`` a registered layout.

    Composition (``render_with_blocks``) and inheritance (``{% extends %}``)
    are not interchangeable in Chirp's page convention. When both are in
    play against the same template, block overrides drop silently and the
    layout structure renders twice.
    """
    issues: list[ContractIssue] = []
    if not page_leaf_templates or kida_env is None:
        return issues

    layout_names = _registered_layout_names(layout_chains)
    if not layout_names:
        return issues

    for template_name in sorted(page_leaf_templates):
        try:
            template = kida_env.get_template(template_name)
        except Exception:
            continue
        meta = template.template_metadata()
        if meta is None or meta.extends is None:
            continue
        extended = meta.extends
        if extended not in layout_names:
            continue
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="composition_extends",
                message=(
                    f"Page template '{template_name}' uses "
                    f"'{{% extends \"{extended}\" %}}' but '{extended}' is "
                    "registered as a layout in this page's chain. Chirp "
                    "composes layouts via render_with_blocks (composition), "
                    "not template inheritance — the page's block overrides "
                    "(e.g. page_scripts, head_extra) will be silently lost "
                    "AND the layout structure will render twice (once via "
                    "kida's extends, once via render_with_layouts). Remove "
                    "the '{% extends %}' clause and rely on the layout chain, "
                    "or extend a non-registered kida partial instead (see "
                    "examples/standalone/oob_layout_chain/ for the partial "
                    "pattern)."
                ),
                template=template_name,
            )
        )

    return issues

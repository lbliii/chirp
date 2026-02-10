"""Layout chain rendering with HX-Target-aware depth.

The renderer composes nested layouts inside-out using kida's
``render_with_blocks()``.  The ``HX-Target`` header determines how
deep to render — only the layouts below the targeted element are
rendered, preserving the outer shell on the client.
"""

from __future__ import annotations

from typing import Any

from kida import Environment

from chirp.pages.types import LayoutChain


def render_with_layouts(
    env: Environment,
    *,
    layout_chain: LayoutChain,
    page_html: str,
    context: dict[str, Any],
    htmx_target: str | None = None,
    is_history_restore: bool = False,
) -> str:
    """Render page content wrapped in its layout chain.

    Uses ``HX-Target`` to determine rendering depth:

    - **No target** (full page load or history restore): render all
      layouts nested, innermost first.
    - **Target matches a layout**: skip layouts at or above the
      matched one; render from the next layout down.
    - **Target matches no layout**: return page HTML as-is (fragment).

    Args:
        env: The kida ``Environment`` for loading layout templates.
        layout_chain: Sequence of layouts from root (outermost) to
            deepest (closest to the page).
        page_html: Pre-rendered page content HTML.
        context: Merged context variables for layout templates.
        htmx_target: Value of ``HX-Target`` header, or ``None``.
        is_history_restore: Whether this is an htmx history restore.

    Returns:
        Rendered HTML string with appropriate layout wrapping.
    """
    layouts = layout_chain.layouts

    if not layouts:
        return page_html

    # Determine which layouts to render
    if is_history_restore or htmx_target is None:
        # Full page render — wrap with all layouts
        start_index = 0
    else:
        idx = layout_chain.find_start_index_for_target(htmx_target)
        if idx is None:
            # Target doesn't match any layout — return as fragment
            return page_html
        start_index = idx

    # Slice layouts: only render from start_index onward
    layouts_to_render = layouts[start_index:]

    # Render inside-out: start with page HTML, wrap with each layout
    # Innermost layout first (last in the list), then outward
    html = page_html
    for layout_info in reversed(layouts_to_render):
        template = env.get_template(layout_info.template_name)
        html = template.render_with_blocks({"content": html}, **context)

    return html

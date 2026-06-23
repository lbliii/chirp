"""Layout chain rendering with HX-Target-aware depth.

The renderer composes nested layouts inside-out using kida's
``render_with_blocks()``.  The ``HX-Target`` header determines how
deep to render — only the layouts below the targeted element are
rendered, preserving the outer shell on the client.
"""

from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp.pages.types import LayoutChain
from chirp.realtime.signal_globals import (
    apply_signal_connect,
    bind_signal_render_path,
    restore_signal_render_path,
)

if TYPE_CHECKING:
    from chirp.templating.fragment_target_registry import FragmentTargetRegistry


def _omit_outer_layout_targets(
    *,
    fragment_target_registry: FragmentTargetRegistry | None,
    htmx_target: str | None,
) -> frozenset[str]:
    """Return registered targets that should omit the matched outer layout."""
    if fragment_target_registry is None or htmx_target is None:
        return frozenset()
    config = fragment_target_registry.get(htmx_target)
    if config is None or not config.omit_outer_layouts:
        return frozenset()
    return frozenset({htmx_target.lstrip("#")})


def render_with_layouts(
    env: Environment,
    *,
    layout_chain: LayoutChain,
    page_html: str,
    context: dict[str, Any],
    htmx_target: str | None = None,
    is_history_restore: bool = False,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> str:
    """Render page content wrapped in its layout chain.

    Uses ``HX-Target`` to determine rendering depth:

    - **No target** (full page load or history restore): render all
      layouts nested, innermost first.
    - **Target matches a replace outlet or omit target**: skip the matched
      outer layout and render any descendant layouts below it.
    - **Target matches an ordinary layout target**: render the matched layout
      and any descendants below it.
    - **Target matches no layout**: return page HTML as-is (fragment).

    Args:
        env: The kida ``Environment`` for loading layout templates.
        layout_chain: Sequence of layouts from root (outermost) to
            deepest (closest to the page).
        page_html: Pre-rendered page content HTML.
        context: Merged context variables for layout templates.
        htmx_target: Value of ``HX-Target`` header, or ``None``.
        is_history_restore: Whether this is an htmx history restore.
        fragment_target_registry: Optional registry for targets that must skip
            the matched outer filesystem layout during boosted navigation.

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
        start_index = layout_chain.start_index_for_htmx_target(
            htmx_target,
            omit_outer_layout_targets=_omit_outer_layout_targets(
                fragment_target_registry=fragment_target_registry,
                htmx_target=htmx_target,
            ),
        )
        if start_index is None:
            # Target doesn't match any layout — return as fragment
            return page_html
        if start_index >= len(layouts):
            return page_html

    # Slice layouts: only render from start_index onward
    layouts_to_render = layouts[start_index:]

    # Render inside-out: start with page HTML, wrap with each layout
    # Innermost layout first (last in the list), then outward
    path = str(context.get("current_path") or "")
    path_token = bind_signal_render_path(path)
    try:
        html = page_html
        for layout_info in reversed(layouts_to_render):
            template = env.get_template(layout_info.template_name)
            html = template.render_with_blocks({"content": html}, **context)

        return apply_signal_connect(html)
    finally:
        restore_signal_render_path(path_token)

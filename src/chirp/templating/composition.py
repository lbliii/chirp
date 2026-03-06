"""Python-first composition vocabulary for shell/content assembly.

ViewRef, RegionUpdate, and PageComposition replace block_name/page_block_name
mental overhead with explicit role-based fields. Routes return these objects;
the render-plan layer decides what to render based on request headers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.pages.types import ContextProvider, LayoutChain


@dataclass(frozen=True, slots=True)
class ViewRef:
    """Reference to a template block with context.

    Used for both main content and region updates (shell actions,
    badges, breadcrumbs, etc.).
    """

    template: str
    block: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RegionUpdate:
    """Out-of-band update for a persistent shell region.

    Renders a ViewRef and delivers it as hx-swap-oob to the named
    region (DOM element ID). Mode defaults to "oob".
    """

    region: str
    view: ViewRef
    mode: str = "oob"


@dataclass(frozen=True, slots=True)
class PageComposition:
    """Explicit page composition with fragment, page block, and regions.

    Replaces Page/LayoutPage block_name/page_block_name with:
    - fragment_block: narrow block for non-boosted fragment requests
    - page_block: wider root for boosted navigation (or full page)
    - regions: shell actions, badges, and other persistent-region refreshes

    Usage::

        PageComposition(
            template="skills/page.html",
            fragment_block="page_content",
            page_block="page_root",
            context={"skills": skills},
            regions=(
                RegionUpdate(
                    region="shell_actions",
                    view=ViewRef(
                        template="chirp/shell_actions.html",
                        block="content",
                        context={"shell_actions": actions},
                    ),
                ),
            ),
        )
    """

    template: str
    fragment_block: str
    page_block: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    regions: tuple[RegionUpdate, ...] = ()
    layout_chain: LayoutChain | None = None
    context_providers: tuple[ContextProvider, ...] = ()

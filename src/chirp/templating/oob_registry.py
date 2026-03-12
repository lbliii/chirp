"""App-level OOB region registry for layout-contract serialization.

Maps OOB block names (e.g. ``breadcrumbs_oob``) to serialization config
(target ID, swap strategy, wrapper behavior). Apps register regions during
setup; the registry is frozen at runtime alongside routes and middleware.

Convention fallback: unregistered blocks use ``block_name.removesuffix("_oob")``
as target ID, ``outerHTML`` swap, and wrapper div.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.templating.render_plan import LayoutContract

OOB_BLOCK_SUFFIX = "_oob"


@dataclass(frozen=True, slots=True)
class OOBRegionConfig:
    """Serialization config for a single OOB region.

    target_id: DOM element ID for hx-swap-oob targeting.
    swap: htmx swap strategy — "innerHTML" or "true" (outerHTML).
    wrap: Whether to wrap in <div id="..." hx-swap-oob="...">. False for
        elements like <title> that embed their own hx-swap-oob attribute.
    """

    target_id: str
    swap: str = "innerHTML"
    wrap: bool = True


@dataclass(slots=True)
class OOBRegistry:
    """App-level registry mapping OOB block names to serialization config.

    Mutable during setup, frozen at runtime (same lifecycle as routes).
    """

    _regions: dict[str, OOBRegionConfig] = field(default_factory=dict)
    _frozen: bool = False
    _contract_cache: dict[str, LayoutContract] = field(default_factory=dict)
    _contract_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def register(self, block_name: str, config: OOBRegionConfig) -> None:
        if self._frozen:
            msg = "Cannot modify OOB registry after app has started."
            raise RuntimeError(msg)
        self._regions[block_name] = config

    def freeze(self) -> None:
        self._frozen = True

    def get(self, block_name: str) -> OOBRegionConfig | None:
        return self._regions.get(block_name)

    def resolve_target(self, block_name: str) -> str:
        """Resolve block name to target ID. Registry first, convention fallback."""
        config = self._regions.get(block_name)
        if config is not None:
            return config.target_id
        return block_name.removesuffix(OOB_BLOCK_SUFFIX)

    def resolve_serialization(self, target_id: str) -> tuple[str, bool]:
        """Return (swap, wrap) for a target ID. Convention default: outerHTML + wrap."""
        for config in self._regions.values():
            if config.target_id == target_id:
                return config.swap, config.wrap
        return "true", True

    @property
    def registered_blocks(self) -> frozenset[str]:
        return frozenset(self._regions)

    def get_or_build_contract(
        self,
        adapter: Any,
        template_name: str,
    ) -> LayoutContract:
        """Return cached LayoutContract, building on first access."""
        from chirp.templating.render_plan import build_layout_contract

        with self._contract_lock:
            contract = self._contract_cache.get(template_name)
            if contract is None:
                contract = build_layout_contract(adapter, template_name, oob_registry=self)
                self._contract_cache[template_name] = contract
            return contract

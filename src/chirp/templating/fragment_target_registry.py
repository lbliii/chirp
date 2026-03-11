"""App-level fragment target registry for HTMX content-region block selection.

Maps target IDs (e.g. ``page-root``) to fragment_block config. When HX-Target
matches a registered target, Chirp uses the registry's fragment_block instead
of composition.page_block. Apps register targets during setup; the registry
is frozen at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FragmentTargetConfig:
    """Block config for a single fragment target.

    fragment_block: Block to render when HX-Target matches (e.g. page_root_inner).
    triggers_shell_update: When True, swapping this target triggers shell_actions OOB
        (breadcrumbs, sidebar, topbar actions). Use False for narrow content swaps
        (e.g. page-content-inner) that should not update the shell.
    """

    fragment_block: str
    triggers_shell_update: bool = True


@dataclass(slots=True)
class FragmentTargetRegistry:
    """App-level registry mapping target IDs to fragment block config.

    Mutable during setup, frozen at runtime (same lifecycle as routes).
    """

    _targets: dict[str, FragmentTargetConfig] = field(default_factory=dict)
    _frozen: bool = False

    def register(
        self,
        target_id: str,
        *,
        fragment_block: str,
        triggers_shell_update: bool = True,
    ) -> None:
        if self._frozen:
            msg = "Cannot modify fragment target registry after app has started."
            raise RuntimeError(msg)
        target_id = target_id.lstrip("#")
        self._targets[target_id] = FragmentTargetConfig(
            fragment_block=fragment_block,
            triggers_shell_update=triggers_shell_update,
        )

    def freeze(self) -> None:
        self._frozen = True

    def get(self, target_id: str) -> FragmentTargetConfig | None:
        return self._targets.get(target_id.lstrip("#"))

    def is_content_target(self, target_id: str) -> bool:
        """Return True when target expects fragment response (not full page_block)."""
        return target_id.lstrip("#") in self._targets

    @property
    def registered_targets(self) -> frozenset[str]:
        return frozenset(self._targets)

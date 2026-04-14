"""App-level fragment target registry for HTMX content-region block selection.

Maps target IDs (e.g. ``page-root``) to fragment_block config. When HX-Target
matches a registered target, Chirp uses the registry's fragment_block instead
of composition.page_block. Apps can group related targets into a page shell
contract so app-level layout expectations are explicit and contract-checkable.
The registry is mutable during setup and frozen at runtime.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PageShellTarget:
    """A single target participating in a page shell contract."""

    target_id: str
    fragment_block: str
    triggers_shell_update: bool = True
    required: bool = True
    description: str = ""
    scope_name: str | None = None
    omit_outer_layouts: bool = False


@dataclass(frozen=True, slots=True)
class PageShellContract:
    """Named group of fragment targets defining an app shell contract."""

    name: str
    targets: tuple[PageShellTarget, ...]
    description: str = ""

    @property
    def required_fragment_blocks(self) -> frozenset[str]:
        return frozenset(target.fragment_block for target in self.targets if target.required)


@dataclass(frozen=True, slots=True)
class FragmentTargetConfig:
    """Block config for a single fragment target.

    **Layers (see UI layers guide):** targets that swap **page content** inside
    ``#page-content`` may still set ``triggers_shell_update`` so **shell regions**
    (topbar ``shell_actions``, title, etc.) refresh via OOB after the primary swap.

    fragment_block: Block to render when HX-Target matches (e.g. page_root_inner).
    triggers_shell_update: When True, this swap participates in shell negotiation
        (e.g. ``shell_actions`` OOB). Use False for **narrow** in-page swaps
        (e.g. ``#page-content-inner``) that must not refresh the app shell.
    omit_outer_layouts: When True, boosted responses for this HX-Target skip
        composing filesystem layouts (page HTML only). Use for marketing shells
        where the outlet wraps the whole ``{% block content %}`` and re-applying
        the root layout would duplicate header/footer inside the outlet.
    """

    fragment_block: str
    triggers_shell_update: bool = True
    contract_name: str | None = None
    required: bool = False
    description: str = ""
    scope_name: str | None = None
    omit_outer_layouts: bool = False


@dataclass(slots=True)
class FragmentTargetRegistry:
    """App-level registry mapping target IDs to fragment block config.

    Mutable during setup, frozen at runtime (same lifecycle as routes).
    """

    _targets: dict[str, FragmentTargetConfig] = field(default_factory=dict)
    _contracts: dict[str, PageShellContract] = field(default_factory=dict)
    _frozen: bool = False

    def register(
        self,
        target_id: str,
        *,
        fragment_block: str,
        triggers_shell_update: bool = True,
        contract_name: str | None = None,
        required: bool = False,
        description: str = "",
        scope_name: str | None = None,
        omit_outer_layouts: bool = False,
    ) -> None:
        if self._frozen:
            msg = "Cannot modify fragment target registry after app has started."
            raise RuntimeError(msg)
        target_id = target_id.lstrip("#")
        self._targets[target_id] = FragmentTargetConfig(
            fragment_block=fragment_block,
            triggers_shell_update=triggers_shell_update,
            contract_name=contract_name,
            required=required,
            description=description,
            scope_name=scope_name,
            omit_outer_layouts=omit_outer_layouts,
        )

    def register_contract(self, contract: PageShellContract) -> None:
        """Register a named page shell contract and all of its targets.

        Multiple contracts are allowed (e.g. primary app shell plus a section
        shell). Target ids must be unique across the registry; later
        registrations override earlier ones for the same target id.
        """
        if self._frozen:
            msg = "Cannot modify fragment target registry after app has started."
            raise RuntimeError(msg)
        self._contracts[contract.name] = contract
        for target in contract.targets:
            self.register(
                target.target_id,
                fragment_block=target.fragment_block,
                triggers_shell_update=target.triggers_shell_update,
                contract_name=contract.name,
                required=target.required,
                description=target.description,
                scope_name=target.scope_name,
                omit_outer_layouts=target.omit_outer_layouts,
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

    @property
    def registered_contracts(self) -> tuple[PageShellContract, ...]:
        return tuple(self._contracts.values())

    @property
    def required_fragment_blocks(self) -> frozenset[str]:
        return frozenset(
            config.fragment_block for config in self._targets.values() if config.required
        )

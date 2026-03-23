"""Route-scoped shell action models and merge helpers.

Nested filesystem routes can contribute actions for persistent shell regions
such as the global top bar. Child routes inherit parent contributions by
default, may override actions by stable ``id``, remove inherited actions, or
replace an entire zone.

Stable DOM id for the actions slot: import ``SHELL_ACTIONS_TARGET`` from
``chirp.shell_actions`` or ``chirp.shell_regions`` (same constant). See the
UI layers guide in ``site/content/docs/guides/ui-layers.md``.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from chirp.shell_actions import (
    SHELL_ACTIONS_BLOCK,
    SHELL_ACTIONS_CONTEXT_KEY,
    SHELL_ACTIONS_TARGET,
    SHELL_ACTIONS_TEMPLATE,
)

__all__ = [
    "SHELL_ACTIONS_BLOCK",
    "SHELL_ACTIONS_CONTEXT_KEY",
    "SHELL_ACTIONS_TARGET",
    "SHELL_ACTIONS_TEMPLATE",
    "ShellAction",
    "ShellActionZone",
    "ShellActions",
    "ShellMenuItem",
    "ShellSubmitSurface",
    "merge_shell_actions",
    "normalize_shell_actions",
    "shell_actions_fragment",
    "validate_shell_actions",
]

type ShellActionKind = Literal["link", "button", "menu", "form"]
type ShellActionVariant = Literal["default", "primary", "secondary", "danger"]
type ShellActionZoneName = Literal["primary", "controls", "overflow"]
type ShellActionZoneMode = Literal["merge", "replace"]
type ShellSubmitSurface = Literal["btn", "shimmer", "pulsing"]

SHELL_ACTION_ZONE_NAMES: tuple[ShellActionZoneName, ...] = ("primary", "controls", "overflow")


@dataclass(frozen=True, slots=True)
class ShellMenuItem:
    """A menu item rendered inside a shell action dropdown."""

    label: str = ""
    href: str | None = None
    action: str | None = None
    variant: ShellActionVariant = "default"
    icon: str | None = None
    divider: bool = False

    def get(self, key: str, default: object = None) -> object:
        """Mapping-like accessor so templates can use dict-style lookups."""
        value = getattr(self, key, default)
        return default if value is None else value


@dataclass(frozen=True, slots=True)
class ShellAction:
    """A single action contribution for a shell region."""

    id: str
    label: str
    kind: ShellActionKind = "link"
    href: str | None = None
    action: str | None = None
    variant: ShellActionVariant = "default"
    icon: str | None = None
    size: str = "sm"
    disabled: bool = False
    menu_items: tuple[ShellMenuItem, ...] = ()
    # kind="form": POST form with optional HTMX attributes (rendered by chirp-ui).
    form_action: str | None = None
    form_method: str = "post"
    hidden_fields: tuple[tuple[str, str], ...] = ()
    include_csrf: bool = True
    hx_post: str | None = None
    hx_target: str | None = None
    hx_swap: str | None = None
    hx_disinherit: str | None = None
    submit_surface: ShellSubmitSurface = "btn"
    #: Extra HTML attributes for ``kind="link"`` / ``kind="button"`` (passed to ``btn``, e.g. HTMX).
    #: Not used for ``kind="form"`` (form actions use dedicated fields).
    attrs: str = ""

    def as_menu_item(self) -> ShellMenuItem:
        """Convert a button/link action to a dropdown-compatible menu item."""
        return ShellMenuItem(
            label=self.label,
            href=self.href,
            action=self.action,
            variant=self.variant,
            icon=self.icon,
        )


@dataclass(frozen=True, slots=True)
class ShellActionZone:
    """A zone contribution with explicit merge semantics."""

    items: tuple[ShellAction, ...] = ()
    remove: tuple[str, ...] = ()
    mode: ShellActionZoneMode = "merge"

    def __bool__(self) -> bool:
        return bool(self.items or self.remove)

    @property
    def overflow_items(self) -> tuple[ShellMenuItem, ...]:
        """Dropdown-compatible items for overflow rendering."""
        return tuple(item.as_menu_item() for item in self.items)


@dataclass(frozen=True, slots=True)
class ShellActions:
    """Resolved shell actions for persistent chrome regions."""

    primary: ShellActionZone = field(default_factory=ShellActionZone)
    controls: ShellActionZone = field(default_factory=ShellActionZone)
    overflow: ShellActionZone = field(default_factory=ShellActionZone)
    target: str = SHELL_ACTIONS_TARGET

    def __post_init__(self) -> None:
        validate_shell_actions(self)

    @property
    def has_items(self) -> bool:
        """Whether any zone currently contains rendered actions."""
        return any(bool(getattr(self, zone_name).items) for zone_name in SHELL_ACTION_ZONE_NAMES)

    def __bool__(self) -> bool:
        return True


def merge_shell_actions(
    parent: ShellActions | None,
    child: ShellActions | None,
) -> ShellActions | None:
    """Merge route-scoped shell actions from parent to child."""
    if parent is None:
        return child
    if child is None:
        return parent

    target = child.target or parent.target
    return ShellActions(
        primary=_merge_zone(parent.primary, child.primary, "primary"),
        controls=_merge_zone(parent.controls, child.controls, "controls"),
        overflow=_merge_zone(parent.overflow, child.overflow, "overflow"),
        target=target,
    )


def normalize_shell_actions(value: Any) -> ShellActions | None:
    """Normalize a context value into ``ShellActions``."""
    if value is None:
        return None
    if isinstance(value, ShellActions):
        validate_shell_actions(value)
        return value
    msg = f"shell_actions must be a ShellActions instance. Got {type(value).__name__} instead."
    raise TypeError(msg)


def shell_actions_fragment(actions: ShellActions | None) -> tuple[str, str, str] | None:
    """Return the template, block, and target for shell OOB rendering."""
    if actions is None:
        return None
    return (SHELL_ACTIONS_TEMPLATE, SHELL_ACTIONS_BLOCK, actions.target)


def validate_shell_actions(actions: ShellActions) -> None:
    """Validate zone contents and stable action ids."""
    for zone_name in SHELL_ACTION_ZONE_NAMES:
        zone = getattr(actions, zone_name)
        if zone.mode == "replace" and zone.remove:
            msg = f"shell_actions.{zone_name} cannot set remove= when mode='replace'"
            raise ValueError(msg)
        _ensure_unique_ids(zone.items, zone_name)
        for item in zone.items:
            _validate_shell_action_item(item, zone_name)
        if zone.mode == "replace":
            continue
        for action_id in zone.remove:
            if not action_id:
                msg = f"shell_actions.{zone_name}.remove cannot contain empty ids"
                raise ValueError(msg)


def _merge_zone(
    parent: ShellActionZone,
    child: ShellActionZone,
    zone_name: str,
) -> ShellActionZone:
    """Merge a child zone onto an inherited parent zone."""
    if child.mode == "replace":
        _ensure_unique_ids(child.items, zone_name)
        return ShellActionZone(items=child.items, mode="replace")

    inherited = {item.id: item for item in parent.items if item.id not in child.remove}
    for item in child.items:
        inherited[item.id] = item

    merged = ShellActionZone(items=tuple(inherited.values()))
    _ensure_unique_ids(merged.items, zone_name)
    return merged


def _validate_shell_action_item(item: ShellAction, zone_name: str) -> None:
    """Reject invalid field combinations for each action kind."""
    if item.kind == "form":
        if zone_name == "overflow":
            msg = "shell_actions.overflow cannot use kind='form' (use primary or controls)"
            raise ValueError(msg)
        if not item.form_action:
            msg = f"shell_actions.{zone_name} action {item.id!r} kind=form requires form_action"
            raise ValueError(msg)
        if item.form_method.lower() != "post":
            msg = f"shell_actions.{zone_name} action {item.id!r}: only form_method='post' is supported"
            raise ValueError(msg)
        if item.attrs:
            msg = (
                f"shell_actions.{zone_name} action {item.id!r}: "
                "attrs is only valid for kind='link' or 'button'"
            )
            raise ValueError(msg)
        return
    if item.form_action is not None:
        msg = f"shell_actions.{zone_name} action {item.id!r}: form_action is only valid for kind='form'"
        raise ValueError(msg)
    if item.hidden_fields:
        msg = f"shell_actions.{zone_name} action {item.id!r}: hidden_fields is only valid for kind='form'"
        raise ValueError(msg)
    if not item.include_csrf:
        msg = f"shell_actions.{zone_name} action {item.id!r}: include_csrf is only meaningful for kind='form'"
        raise ValueError(msg)
    if item.hx_post is not None or item.hx_target is not None or item.hx_swap is not None:
        msg = f"shell_actions.{zone_name} action {item.id!r}: HTMX fields are only valid for kind='form'"
        raise ValueError(msg)
    if item.hx_disinherit is not None:
        msg = f"shell_actions.{zone_name} action {item.id!r}: hx_disinherit is only valid for kind='form'"
        raise ValueError(msg)
    if item.submit_surface != "btn":
        msg = f"shell_actions.{zone_name} action {item.id!r}: submit_surface is only valid for kind='form'"
        raise ValueError(msg)
    if item.attrs and item.kind not in ("link", "button"):
        msg = f"shell_actions.{zone_name} action {item.id!r}: attrs is only valid for kind='link' or 'button'"
        raise ValueError(msg)


def _ensure_unique_ids(items: tuple[ShellAction, ...], zone_name: str) -> None:
    seen: set[str] = set()
    for item in items:
        if not item.id:
            msg = f"shell_actions.{zone_name} items require a non-empty id"
            raise ValueError(msg)
        if item.id in seen:
            msg = f"Duplicate shell action id {item.id!r} in zone {zone_name!r}"
            raise ValueError(msg)
        seen.add(item.id)

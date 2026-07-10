"""Internal planner for live-preserving development template reloads.

This module deliberately stops before browser mutation.  It snapshots Kida's
structural manifests, invalidates the real environment after a file edit, and
classifies the edit as ``patch``, ``diagnose``, or ``reload``.  A patch plan is
only permission to re-request the real route through htmx; it never contains
rendered HTML and still requires response validation before a swap.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from kida import Environment

if TYPE_CHECKING:
    from kida.analysis.metadata import TemplateStructureManifest

    from chirp.app.hypermedia_program import HypermediaProgram
    from chirp.templating.fragment_target_registry import FragmentTargetRegistry

type TemplateReloadOutcome = Literal["patch", "diagnose", "reload"]


@dataclass(frozen=True, slots=True)
class TemplateReloadTarget:
    """One frozen fragment-target mapping relevant to a template block."""

    target_id: str
    block_name: str
    scope_name: str | None


@dataclass(frozen=True, slots=True)
class TemplateReloadEntry:
    """Immutable source-backed Kida structure used by the planner."""

    template_name: str
    source_filename: str
    extends: str | None
    blocks: tuple[tuple[str, str], ...]
    dependencies: frozenset[str]
    route_paths: tuple[str, ...]
    targets: tuple[TemplateReloadTarget, ...]

    @property
    def block_hashes(self) -> dict[str, str]:
        """Return a disposable name-to-hash mapping."""
        return dict(self.blocks)


@dataclass(frozen=True, slots=True)
class TemplateReloadInventory:
    """Frozen reachable-template inventory for one planner connection."""

    entries: tuple[TemplateReloadEntry, ...] = ()

    def entries_for_source(self, filename: str | Path) -> tuple[TemplateReloadEntry, ...]:
        resolved = str(Path(filename).resolve())
        return tuple(entry for entry in self.entries if entry.source_filename == resolved)

    def replace_entry(self, updated: TemplateReloadEntry) -> TemplateReloadInventory:
        entries = tuple(
            updated if entry.template_name == updated.template_name else entry
            for entry in self.entries
        )
        return TemplateReloadInventory(
            tuple(sorted(entries, key=lambda entry: entry.template_name))
        )


@dataclass(frozen=True, slots=True)
class TemplateReloadSurface:
    """Browser/route facts that must be proven before a patch is eligible.

    Defaults intentionally fail closed.  The later browser adapter owns
    collecting these facts; the planner never guesses them from source text.
    ``connection_boundary_targets`` contains a connection owner plus any target
    at or above that owner, all of which are forbidden patch targets.
    """

    reachable_templates: frozenset[str] = frozenset()
    route_target_ids: frozenset[str] = frozenset()
    live_target_counts: tuple[tuple[str, int], ...] = ()
    connection_boundary_targets: frozenset[str] = frozenset()
    shell_boundary_targets: frozenset[str] = frozenset()
    active_suspense_targets: frozenset[str] = frozenset()
    get_safe: bool = False
    htmx_adapter_available: bool = False

    def target_count(self, target_id: str) -> int:
        return dict(self.live_target_counts).get(target_id, 0)


@dataclass(frozen=True, slots=True)
class TemplateReloadPlan:
    """Redacted planner decision; never a render payload."""

    revision: int
    outcome: TemplateReloadOutcome
    reason: str
    template_name: str | None = None
    changed_blocks: tuple[str, ...] = ()
    added_blocks: tuple[str, ...] = ()
    removed_blocks: tuple[str, ...] = ()
    target_id: str | None = None
    error_type: str | None = None
    error_line: int | None = None
    requires_response_validation: bool = False


def build_template_reload_inventory(
    env: Environment,
    program: HypermediaProgram | None,
    fragment_targets: FragmentTargetRegistry | None,
) -> TemplateReloadInventory:
    """Compile source-backed reachable templates from frozen app state.

    The hypermedia program remains the reachability authority.  This function
    does not scan template directories and skips package/opaque loader entries
    that do not expose a filename.
    """
    if program is None or env.loader is None:
        return TemplateReloadInventory()

    route_paths_by_template: dict[str, set[str]] = {}
    for route in program.routes:
        for template_id in route.template_ids:
            route_paths_by_template.setdefault(template_id, set()).add(route.path)

    registered_targets: list[TemplateReloadTarget] = []
    if fragment_targets is not None:
        for target_id in sorted(fragment_targets.registered_targets):
            config = fragment_targets.get(target_id)
            if config is not None:
                registered_targets.append(
                    TemplateReloadTarget(target_id, config.fragment_block, config.scope_name)
                )

    entries: list[TemplateReloadEntry] = []
    for template_node in program.templates:
        manifest = env.get_template_structure(template_node.name)
        if manifest is None:
            continue
        _source, filename = env.loader.get_source(template_node.name)
        if filename is None:
            continue
        block_names = frozenset(manifest.block_names)
        entries.append(
            TemplateReloadEntry(
                template_name=template_node.name,
                source_filename=str(Path(filename).resolve()),
                extends=manifest.extends,
                blocks=tuple(sorted(manifest.block_hashes.items())),
                dependencies=frozenset(manifest.dependencies),
                route_paths=tuple(sorted(route_paths_by_template.get(template_node.id, ()))),
                targets=tuple(
                    target for target in registered_targets if target.block_name in block_names
                ),
            )
        )

    return TemplateReloadInventory(tuple(sorted(entries, key=lambda entry: entry.template_name)))


class TemplateReloadPlanner:
    """Serialize template edits and publish monotonic redacted decisions."""

    __slots__ = ("_env", "_inventory", "_lock", "_revision")

    def __init__(self, env: Environment, inventory: TemplateReloadInventory) -> None:
        self._env = env
        self._inventory = inventory
        self._lock = threading.Lock()
        self._revision = 0

    @property
    def inventory(self) -> TemplateReloadInventory:
        with self._lock:
            return self._inventory

    def plan_edit(
        self,
        filename: str | Path,
        surface: TemplateReloadSurface,
    ) -> TemplateReloadPlan:
        """Invalidate one edited template and classify it without rendering."""
        with self._lock:
            self._revision += 1
            revision = self._revision
            matches = self._inventory.entries_for_source(filename)
            if not matches:
                return TemplateReloadPlan(revision, "reload", "unknown_template_source")
            if len(matches) != 1:
                return TemplateReloadPlan(revision, "reload", "ambiguous_template_source")

            previous = matches[0]
            self._env.clear_template_cache([previous.template_name])
            try:
                self._env.get_template(previous.template_name)
            except Exception as exc:
                line = getattr(exc, "lineno", None)
                return TemplateReloadPlan(
                    revision,
                    "diagnose",
                    "template_compile_error",
                    template_name=previous.template_name,
                    error_type=type(exc).__name__,
                    error_line=line if isinstance(line, int) else None,
                )

            manifest = self._env.get_template_structure(previous.template_name)
            if manifest is None:
                return TemplateReloadPlan(
                    revision,
                    "diagnose",
                    "template_structure_unavailable",
                    template_name=previous.template_name,
                )

            current = _updated_entry(previous, manifest)
            self._inventory = self._inventory.replace_entry(current)
            return _classify_edit(revision, previous, current, surface)


def _updated_entry(
    previous: TemplateReloadEntry,
    manifest: TemplateStructureManifest,
) -> TemplateReloadEntry:
    block_names = frozenset(manifest.block_names)
    return replace(
        previous,
        extends=manifest.extends,
        blocks=tuple(sorted(manifest.block_hashes.items())),
        dependencies=frozenset(manifest.dependencies),
        targets=tuple(target for target in previous.targets if target.block_name in block_names),
    )


def _classify_edit(
    revision: int,
    previous: TemplateReloadEntry,
    current: TemplateReloadEntry,
    surface: TemplateReloadSurface,
) -> TemplateReloadPlan:
    before = previous.block_hashes
    after = current.block_hashes
    before_names = set(before)
    after_names = set(after)
    added = tuple(sorted(after_names - before_names))
    removed = tuple(sorted(before_names - after_names))
    changed = tuple(
        sorted(name for name in before_names & after_names if before[name] != after[name])
    )

    def decision(
        reason: str,
        *,
        outcome: TemplateReloadOutcome = "reload",
        target_id: str | None = None,
        requires_response_validation: bool = False,
    ) -> TemplateReloadPlan:
        return TemplateReloadPlan(
            revision=revision,
            outcome=outcome,
            reason=reason,
            template_name=previous.template_name,
            changed_blocks=changed,
            added_blocks=added,
            removed_blocks=removed,
            target_id=target_id,
            requires_response_validation=requires_response_validation,
        )

    if added:
        return decision("block_added")
    if removed:
        return decision("block_removed")
    if previous.extends != current.extends:
        return decision("composition_changed")
    if previous.dependencies != current.dependencies:
        return decision("dependencies_changed")
    if not changed:
        return decision("top_level_or_unknown_change")
    if len(changed) != 1:
        return decision("multiple_blocks_changed")
    if not previous.route_paths:
        return decision("not_route_reachable")
    if previous.template_name not in surface.reachable_templates:
        return decision("not_current_route_template")

    block_name = changed[0]
    registered = tuple(target for target in current.targets if target.block_name == block_name)
    route_targets = tuple(
        target for target in registered if target.target_id in surface.route_target_ids
    )
    if not registered:
        return decision("target_unregistered")
    if not route_targets:
        return decision("target_outside_route_scope")
    if len(route_targets) != 1:
        return decision("target_ambiguous")

    target_id = route_targets[0].target_id
    target_count = surface.target_count(target_id)
    if target_count == 0:
        return decision("target_missing", target_id=target_id)
    if target_count != 1:
        return decision("target_duplicate", target_id=target_id)
    if target_id in surface.connection_boundary_targets:
        return decision("connection_boundary", target_id=target_id)
    if target_id in surface.shell_boundary_targets:
        return decision("shell_boundary", target_id=target_id)
    if target_id in surface.active_suspense_targets:
        return decision("active_suspense", target_id=target_id)
    if not surface.get_safe:
        return decision("route_not_safe_get", target_id=target_id)
    if not surface.htmx_adapter_available:
        return decision("htmx_adapter_unavailable", target_id=target_id)

    return decision(
        "registered_live_target",
        outcome="patch",
        target_id=target_id,
        requires_response_validation=True,
    )

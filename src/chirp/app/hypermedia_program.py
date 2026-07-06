"""Immutable internal application model compiled at the freeze boundary.

This module is intentionally not exported from :mod:`chirp`.  It consolidates
stable identities and relationships for internal consumers without replacing
the request-aware render plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

from chirp.errors import ConfigurationError

type Provenance = Literal["declared", "inferred"]
type OriginKind = Literal["handler", "registry", "template"]
type TransitionKind = Literal["route_block", "route_template", "target_block", "template_block"]


def stable_identity(kind: str, *parts: str) -> str:
    """Build a deterministic, collision-resistant semantic identity."""
    encoded = ":".join(quote(part, safe="") for part in parts)
    return f"{kind}:{encoded}"


@dataclass(frozen=True, slots=True)
class SourceOrigin:
    """Public-safe source location for one compiled fact."""

    kind: OriginKind
    identifier: str
    line: int | None = None


@dataclass(frozen=True, slots=True)
class TemplateDeclaration:
    """Setup-time declaration for a dynamically selected template surface."""

    template: str
    blocks: tuple[str, ...]
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class RouteNode:
    """One method-specific route identity."""

    id: str
    path: str
    method: str
    name: str | None
    template_ids: tuple[str, ...]
    origin: SourceOrigin
    provenance: Provenance = "declared"


@dataclass(frozen=True, slots=True)
class TemplateNode:
    """One logical template and its discovered block identities."""

    id: str
    name: str
    block_ids: tuple[str, ...]
    extends: str | None
    is_page: bool
    is_page_leaf: bool
    origin: SourceOrigin
    load_error: str | None = None
    provenance: Provenance = "inferred"


@dataclass(frozen=True, slots=True)
class BlockNode:
    """One named block within a logical template."""

    id: str
    template_id: str
    name: str
    origin: SourceOrigin
    provenance: Provenance = "inferred"


@dataclass(frozen=True, slots=True)
class TargetNode:
    """One registered htmx target and its expected fragment block."""

    id: str
    target_id: str
    fragment_block: str
    required: bool
    contract_name: str | None
    origin: SourceOrigin
    provenance: Provenance = "declared"


@dataclass(frozen=True, slots=True)
class TransitionEdge:
    """A stable relationship between compiled nodes."""

    id: str
    kind: TransitionKind
    source_id: str
    destination_id: str
    resolved: bool
    origin: SourceOrigin
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class HypermediaProgram:
    """Frozen application graph published with runtime state."""

    routes: tuple[RouteNode, ...] = ()
    templates: tuple[TemplateNode, ...] = ()
    blocks: tuple[BlockNode, ...] = ()
    targets: tuple[TargetNode, ...] = ()
    transitions: tuple[TransitionEdge, ...] = ()
    template_declarations: tuple[TemplateDeclaration, ...] = ()

    def __post_init__(self) -> None:
        collections = (
            ("route", self.routes),
            ("template", self.templates),
            ("block", self.blocks),
            ("target", self.targets),
            ("transition", self.transitions),
        )
        for label, values in collections:
            _reject_duplicate_ids(label, values)
        _validate_transitions(self)

    def template(self, name: str) -> TemplateNode | None:
        """Return the template with logical *name*, if compiled."""
        template_id = stable_identity("template", name)
        return next((node for node in self.templates if node.id == template_id), None)

    def block_names(self, template_name: str) -> frozenset[str]:
        """Return discovered block names for *template_name*."""
        template_id = stable_identity("template", template_name)
        return frozenset(node.name for node in self.blocks if node.template_id == template_id)

    @property
    def declared_template_names(self) -> frozenset[str]:
        """Return templates made reachable through explicit declarations."""
        return frozenset(declaration.template for declaration in self.template_declarations)

    @property
    def page_leaf_templates(self) -> tuple[TemplateNode, ...]:
        """Return page leaf templates in deterministic order."""
        return tuple(node for node in self.templates if node.is_page_leaf)

    def target_block_transitions(
        self,
        *,
        target_id: str | None = None,
        template_name: str | None = None,
    ) -> tuple[TransitionEdge, ...]:
        """Query compiled target-to-page-block expectations."""
        source_id = stable_identity("target", target_id) if target_id is not None else None
        template_prefix = (
            stable_identity("block", template_name, "") if template_name is not None else None
        )
        return tuple(
            edge
            for edge in self.transitions
            if edge.kind == "target_block"
            and (source_id is None or edge.source_id == source_id)
            and (template_prefix is None or edge.destination_id.startswith(template_prefix))
        )


def _reject_duplicate_ids(label: str, values: tuple[Any, ...]) -> None:
    seen: set[str] = set()
    for value in values:
        identity = value.id
        if identity in seen:
            raise ConfigurationError(
                f"Duplicate hypermedia program {label} identity {identity!r}. "
                "Use unique route methods, paths, template names, blocks, and targets."
            )
        seen.add(identity)


def _validate_transitions(program: HypermediaProgram) -> None:
    node_ids = {
        *(node.id for node in program.routes),
        *(node.id for node in program.templates),
        *(node.id for node in program.blocks),
        *(node.id for node in program.targets),
    }
    for edge in program.transitions:
        if edge.source_id not in node_ids:
            raise ConfigurationError(
                f"Hypermedia program transition {edge.id!r} has unknown source {edge.source_id!r}."
            )
        if edge.resolved and edge.destination_id not in node_ids:
            raise ConfigurationError(
                f"Hypermedia program transition {edge.id!r} resolves to unknown destination "
                f"{edge.destination_id!r}."
            )

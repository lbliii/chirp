"""Private immutable projection for Contract Explorer consumers.

The projection copies bounded scalar facts from the frozen
:class:`~chirp.app.hypermedia_program.HypermediaProgram` and a finalized
:class:`~chirp.contracts.types.CheckResult`.  It deliberately does not accept an
``App``: construction must not inspect mutable registries, load templates, or
execute route handlers.

This module is internal and is not exported from :mod:`chirp` or
:mod:`chirp.contracts`.  Its records are not a public inspection schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chirp.app.hypermedia_program import HypermediaProgram, SourceOrigin

from .types import CheckResult, ContractCoverage, ContractIssue

type ExplorerNodeKind = Literal["block", "route", "target", "template"]
type FindingBinding = Literal["ambiguous", "bound", "unbound"]


@dataclass(frozen=True, slots=True)
class ExplorerOrigin:
    """One bounded, public-safe logical source copied from compiler output."""

    kind: str
    identifier: str
    line: int | None


@dataclass(frozen=True, slots=True)
class ExplorerNode:
    """One route, template, block, or target copied from the compiler model."""

    id: str
    kind: ExplorerNodeKind
    label: str
    provenance: str
    origin: ExplorerOrigin
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ExplorerEdge:
    """One compiler-authored relationship, including unresolved destinations."""

    id: str
    kind: str
    source_id: str
    destination_id: str
    resolved: bool
    provenance: str
    origin: ExplorerOrigin


@dataclass(frozen=True, slots=True)
class ExplorerFinding:
    """One finalized check finding with honest exact-location correlation."""

    severity: str
    category: str
    message: str
    route: str | None
    template: str | None
    details: str | None
    binding: FindingBinding
    route_node_ids: tuple[str, ...]
    template_node_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExplorerProjection:
    """Complete immutable static topology and finalized check snapshot."""

    nodes: tuple[ExplorerNode, ...]
    edges: tuple[ExplorerEdge, ...]
    findings: tuple[ExplorerFinding, ...]
    coverage: tuple[tuple[str, int], ...]
    analysis_gaps: tuple[str, ...]


# These families are checked today, but the compiler does not yet publish
# topology for them.  Keeping them visible prevents an empty graph from being
# mistaken for proof that an app has none of these relationships.
_STATIC_ANALYSIS_GAPS = (
    "accessibility_topology:not_compiled",
    "auth_topology:not_compiled",
    "form_topology:not_compiled",
    "oob_topology:not_compiled",
    "return_intent_kind:not_compiled",
    "signal_topology:not_compiled",
    "sse_topology:not_compiled",
    "suspense_topology:not_compiled",
)


def build_explorer_projection(
    program: HypermediaProgram,
    result: CheckResult | None,
) -> ExplorerProjection:
    """Copy frozen compiler topology and a finalized check result.

    ``result`` may be ``None`` only for consumers that need to represent an
    unavailable check run.  That state is an explicit analysis gap and never a
    clean result.  Callers must finish mutating a ``CheckResult`` before passing
    it here; all data is copied into frozen tuples before this function returns.
    """
    nodes = _project_nodes(program)
    route_ids_by_path = _index_route_ids(nodes)
    template_ids_by_name = _index_template_ids(nodes)
    findings = (
        _project_findings(result.issues, route_ids_by_path, template_ids_by_name)
        if result is not None
        else ()
    )
    gaps = list(_STATIC_ANALYSIS_GAPS)
    if result is None:
        gaps.append("contract_findings_and_coverage:unavailable")
    return ExplorerProjection(
        nodes=nodes,
        edges=tuple(
            sorted(
                (
                    ExplorerEdge(
                        id=edge.id,
                        kind=edge.kind,
                        source_id=edge.source_id,
                        destination_id=edge.destination_id,
                        resolved=edge.resolved,
                        provenance=edge.provenance,
                        origin=_project_origin(edge.origin),
                    )
                    for edge in program.transitions
                ),
                key=lambda edge: edge.id,
            )
        ),
        findings=findings,
        coverage=_project_coverage(result.coverage) if result is not None else (),
        analysis_gaps=tuple(sorted(gaps)),
    )


def _project_origin(origin: SourceOrigin) -> ExplorerOrigin:
    return ExplorerOrigin(origin.kind, origin.identifier, origin.line)


def _project_nodes(program: HypermediaProgram) -> tuple[ExplorerNode, ...]:
    nodes = [
        ExplorerNode(
            id=node.id,
            kind="route",
            label=f"{node.method} {node.path}",
            provenance=node.provenance,
            origin=_project_origin(node.origin),
            attributes=(
                ("method", node.method),
                ("name", node.name or ""),
                ("path", node.path),
            ),
        )
        for node in program.routes
    ]
    nodes.extend(
        ExplorerNode(
            id=node.id,
            kind="template",
            label=node.name,
            provenance=node.provenance,
            origin=_project_origin(node.origin),
            attributes=(
                ("extends", node.extends or ""),
                ("is_page", _bool_text(node.is_page)),
                ("is_page_leaf", _bool_text(node.is_page_leaf)),
                ("name", node.name),
            ),
        )
        for node in program.templates
    )
    nodes.extend(
        ExplorerNode(
            id=node.id,
            kind="block",
            label=node.name,
            provenance=node.provenance,
            origin=_project_origin(node.origin),
            attributes=(("name", node.name), ("template_id", node.template_id)),
        )
        for node in program.blocks
    )
    nodes.extend(
        ExplorerNode(
            id=node.id,
            kind="target",
            label=node.target_id,
            provenance=node.provenance,
            origin=_project_origin(node.origin),
            attributes=(
                ("contract_name", node.contract_name or ""),
                ("fragment_block", node.fragment_block),
                ("required", _bool_text(node.required)),
                ("target_id", node.target_id),
            ),
        )
        for node in program.targets
    )
    return tuple(sorted(nodes, key=lambda node: node.id))


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _index_route_ids(nodes: tuple[ExplorerNode, ...]) -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = {}
    for node in nodes:
        if node.kind != "route":
            continue
        path = dict(node.attributes)["path"]
        index.setdefault(path, []).append(node.id)
    return {path: tuple(sorted(ids)) for path, ids in index.items()}


def _index_template_ids(nodes: tuple[ExplorerNode, ...]) -> dict[str, tuple[str, ...]]:
    return {dict(node.attributes)["name"]: (node.id,) for node in nodes if node.kind == "template"}


def _project_findings(
    issues: list[ContractIssue],
    route_ids_by_path: dict[str, tuple[str, ...]],
    template_ids_by_name: dict[str, tuple[str, ...]],
) -> tuple[ExplorerFinding, ...]:
    findings = []
    for issue in issues:
        route_ids = route_ids_by_path.get(issue.route, ()) if issue.route is not None else ()
        template_ids = (
            template_ids_by_name.get(issue.template, ()) if issue.template is not None else ()
        )
        findings.append(
            ExplorerFinding(
                severity=issue.severity.value,
                category=issue.category,
                message=issue.message,
                route=issue.route,
                template=issue.template,
                details=issue.details,
                binding=_finding_binding(issue, route_ids, template_ids),
                route_node_ids=route_ids,
                template_node_ids=template_ids,
            )
        )
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.severity,
                finding.category,
                finding.route or "",
                finding.template or "",
                finding.message,
                finding.details or "",
            ),
        )
    )


def _finding_binding(
    issue: ContractIssue,
    route_ids: tuple[str, ...],
    template_ids: tuple[str, ...],
) -> FindingBinding:
    has_location = issue.route is not None or issue.template is not None
    missing_location = (issue.route is not None and not route_ids) or (
        issue.template is not None and not template_ids
    )
    if not has_location or missing_location:
        return "unbound"
    if len(route_ids) > 1 or len(template_ids) > 1:
        return "ambiguous"
    return "bound"


def _project_coverage(coverage: ContractCoverage) -> tuple[tuple[str, int], ...]:
    values = (
        ("fragment_targets_registered", coverage.fragment_targets_registered),
        ("mounted_page_routes", coverage.mounted_page_routes),
        ("mounted_page_routes_with_contract", coverage.mounted_page_routes_with_contract),
        ("oob_regions_registered", coverage.oob_regions_registered),
        ("page_shell_contracts", coverage.page_shell_contracts),
        ("page_shell_required_blocks", coverage.page_shell_required_blocks),
        ("post_routes", coverage.post_routes),
        ("post_routes_with_form_contract", coverage.post_routes_with_form_contract),
        ("webmcp_parameters_declared", coverage.webmcp_parameters_declared),
        ("webmcp_projections_compiled", coverage.webmcp_projections_compiled),
        ("webmcp_projections_declared", coverage.webmcp_projections_declared),
    )
    return tuple(sorted(values))

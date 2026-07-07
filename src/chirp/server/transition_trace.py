"""Correlate runtime return traces with the frozen hypermedia program."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from chirp.app.hypermedia_program import HypermediaProgram, stable_identity
from chirp.templating.trace import ReturnTrace

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.routing.route import Route

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "QUERY"})
_MAX_TRANSITIONS = 16
_MAX_DESCRIPTION = 240


def _matched_route_id(
    program: HypermediaProgram,
    route: Route,
    method: str,
) -> str | None:
    candidates = [node for node in program.routes if node.path == route.path]
    exact = next((node for node in candidates if node.method == method), None)
    if exact is not None:
        return exact.id
    if method == "HEAD":
        fallback = next((node for node in candidates if node.method == "GET"), None)
        if fallback is not None:
            return fallback.id
    return candidates[0].id if len(candidates) == 1 else None


def _request_mode(request: Request) -> str:
    if request.is_boosted:
        return "boosted"
    if request.is_narrow_fragment:
        return "targeted"
    if request.is_htmx:
        return "htmx"
    return "normal"


def _mode_tags(request: Request, trace: ReturnTrace, request_mode: str) -> tuple[str, ...]:
    tags = [request_mode]
    if request.method not in _SAFE_METHODS:
        tags.append("mutation")
    if trace.category == "oob":
        tags.append("oob")
    if trace.category == "suspense":
        tags.append("suspense")
    if trace.sse:
        tags.append("sse")
    return tuple(tags)


def _node_labels(program: HypermediaProgram) -> dict[str, str]:
    labels = {node.id: f"{node.method} {node.path}" for node in program.routes}
    template_names = {node.id: node.name for node in program.templates}
    labels.update({node.id: f"template {node.name}" for node in program.templates})
    labels.update(
        {
            node.id: f"block {node.name} in {template_names.get(node.template_id, node.template_id)}"
            for node in program.blocks
        }
    )
    labels.update({node.id: f"target #{node.target_id}" for node in program.targets})
    return labels


def _relevant_transition_ids(
    program: HypermediaProgram,
    *,
    route_id: str,
    template: str | None,
    block: str | None,
    target_id: str | None,
) -> tuple[str, ...]:
    template_id = stable_identity("template", template) if template else None
    block_id = stable_identity("block", template, block) if template and block else None
    target_node_id = stable_identity("target", target_id) if target_id else None
    destination_ids = {value for value in (template_id, block_id) if value is not None}

    matches: list[str] = []
    for edge in program.transitions:
        route_edge = edge.source_id == route_id and (
            not destination_ids or edge.destination_id in destination_ids
        )
        target_edge = (
            target_node_id is not None
            and edge.source_id == target_node_id
            and (block_id is None or edge.destination_id == block_id)
        )
        template_edge = (
            template_id is not None
            and block_id is not None
            and edge.source_id == template_id
            and edge.destination_id == block_id
        )
        if route_edge or target_edge or template_edge:
            matches.append(edge.id)
    return tuple(matches[:_MAX_TRANSITIONS])


def _transition_descriptions(
    program: HypermediaProgram,
    transition_ids: tuple[str, ...],
) -> tuple[str, ...]:
    labels = _node_labels(program)
    wanted = set(transition_ids)
    descriptions: list[str] = []
    for edge in program.transitions:
        if edge.id not in wanted:
            continue
        source = labels.get(edge.source_id, edge.source_id)
        destination = labels.get(edge.destination_id, edge.destination_id)
        resolution = "resolved" if edge.resolved else "unresolved"
        value = f"{edge.kind}: {source} -> {destination} ({resolution})"
        descriptions.append(value[:_MAX_DESCRIPTION])
    return tuple(descriptions)


def correlate_return_trace(
    trace: ReturnTrace,
    *,
    request: Request,
    route: Route,
    program: HypermediaProgram,
    status: int,
) -> ReturnTrace:
    """Return *trace* enriched with stable compiled/runtime identities."""
    route_id = _matched_route_id(program, route, request.method)
    if route_id is None:
        return replace(trace, status=status, route_path=route.path)

    request_mode = _request_mode(request)
    mode_tags = _mode_tags(request, trace, request_mode)
    requested_target = request.htmx_target_id
    compiled_target_ids = {node.target_id for node in program.targets}
    target_id = requested_target if requested_target in compiled_target_ids else None
    transition_ids = _relevant_transition_ids(
        program,
        route_id=route_id,
        template=trace.template,
        block=trace.block,
        target_id=target_id,
    )
    observation_id = stable_identity(
        "observation",
        route_id,
        request_mode,
        ",".join(mode_tags),
        trace.return_type,
        trace.template or "",
        trace.block or "",
        stable_identity("target", target_id) if target_id else "",
    )
    return replace(
        trace,
        status=status,
        route_id=route_id,
        route_path=route.path,
        observation_id=observation_id,
        request_mode=request_mode,
        mode_tags=mode_tags,
        compiled_transition_ids=transition_ids,
        transition_descriptions=_transition_descriptions(program, transition_ids),
    )

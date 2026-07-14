"""Private immutable signal topology compiled at the application freeze boundary."""

from __future__ import annotations

import hashlib
import inspect
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from chirp.errors import ConfigurationError

from .hypermedia_program import HypermediaProgram, SourceOrigin, stable_identity

type _ProducerKind = Literal["primary", "derived"]
type _SourceKind = Literal["lazy", "push", "derived"]
type _BindingEvidence = Literal["helper", "marker", "dynamic"]
type _Ownership = Literal["resolved", "missing", "ambiguous"]
type _SignalEdgeKind = Literal["depends_on", "renders_to", "owned_by", "activates"]

_TEMPLATE_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HELPER_CALL = re.compile(r"\bsignal(?:_block|_bind|_attrs)?\s*\(")
_LITERAL_HELPER = re.compile(r"\bsignal(?:_block|_bind|_attrs)?\s*\(\s*[\"'](?P<name>[^\"']+)[\"']")
_RAW_BINDING = re.compile(
    r"\b(?:sse-swap|data-chirp-signal)\s*=\s*[\"'](?P<name>[^\"']+)[\"']",
    re.IGNORECASE,
)
_HELPER_CONNECTION = re.compile(r"\bsignal_connect\s*\(\s*\)")
_LITERAL_CONNECTION = re.compile(
    r"\b(?:sse-connect|hx-sse:connect)\s*=\s*[\"'](?P<url>[^\"']+)[\"']",
    re.IGNORECASE,
)
_SIGNAL_STREAM_PATH = "/_chirp/live"
_logger = logging.getLogger("chirp.app.signal_graph")


@dataclass(frozen=True, slots=True)
class _SignalProducerNode:
    id: str
    name: str
    kind: _ProducerKind
    source_kind: _SourceKind
    dependencies: tuple[str, ...]
    audience: str
    coalesce: bool
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _SignalBindingNode:
    id: str
    signal_name: str | None
    template_id: str
    evidence: _BindingEvidence
    ownership: _Ownership
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _SignalConnectionNode:
    id: str
    template_id: str
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _SignalEdge:
    id: str
    kind: _SignalEdgeKind
    source_id: str
    destination_id: str
    resolved: bool
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _SignalGraph:
    """Frozen producer/dependency/sink topology; never contains live values."""

    producers: tuple[_SignalProducerNode, ...] = ()
    bindings: tuple[_SignalBindingNode, ...] = ()
    connections: tuple[_SignalConnectionNode, ...] = ()
    edges: tuple[_SignalEdge, ...] = ()

    def __post_init__(self) -> None:
        for label, values in (
            ("producer", self.producers),
            ("binding", self.bindings),
            ("connection", self.connections),
            ("edge", self.edges),
        ):
            _reject_duplicate_ids(label, values)
        _validate_edges(self)

    def producer(self, name: str) -> _SignalProducerNode | None:
        producer_id = stable_identity("signal_producer", name)
        return next((node for node in self.producers if node.id == producer_id), None)

    def sink_ids_for(self, name: str) -> tuple[str, ...]:
        """Return direct and transitively-derived bindings reachable from *name*."""
        producer_id = stable_identity("signal_producer", name)
        reachable = {producer_id}
        changed = True
        while changed:
            changed = False
            for edge in self.edges:
                if (
                    edge.kind == "depends_on"
                    and edge.source_id in reachable
                    and edge.destination_id not in reachable
                ):
                    reachable.add(edge.destination_id)
                    changed = True
        return tuple(
            sorted(
                edge.destination_id
                for edge in self.edges
                if edge.kind == "renders_to" and edge.resolved and edge.source_id in reachable
            )
        )

    @property
    def topology_digest(self) -> str:
        """Stable digest of the public-safe, telemetry-free topology receipt."""
        receipt = (
            tuple(
                (
                    node.id,
                    node.name,
                    node.kind,
                    node.source_kind,
                    node.dependencies,
                    node.audience,
                    node.coalesce,
                    node.origin,
                )
                for node in self.producers
            ),
            tuple(
                (
                    node.id,
                    node.signal_name,
                    node.template_id,
                    node.evidence,
                    node.ownership,
                    node.origin,
                )
                for node in self.bindings
            ),
            tuple((node.id, node.template_id, node.origin) for node in self.connections),
            tuple(
                (
                    edge.id,
                    edge.kind,
                    edge.source_id,
                    edge.destination_id,
                    edge.resolved,
                    edge.origin,
                )
                for edge in self.edges
            ),
        )
        return hashlib.sha256(repr(receipt).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _BindingFact:
    signal_name: str | None
    evidence: _BindingEvidence
    start: int
    line: int


def _reject_duplicate_ids(label: str, values: tuple[Any, ...]) -> None:
    seen: set[str] = set()
    for value in values:
        if value.id in seen:
            raise ConfigurationError(f"Duplicate signal graph {label} identity {value.id!r}.")
        seen.add(value.id)


def _validate_edges(graph: _SignalGraph) -> None:
    producer_ids = {node.id for node in graph.producers}
    binding_ids = {node.id for node in graph.bindings}
    connection_ids = {node.id for node in graph.connections}
    for edge in graph.edges:
        if not edge.resolved:
            continue
        valid = {
            "depends_on": edge.source_id in producer_ids and edge.destination_id in producer_ids,
            "renders_to": edge.source_id in producer_ids and edge.destination_id in binding_ids,
            "owned_by": edge.source_id in binding_ids and edge.destination_id in connection_ids,
            "activates": edge.source_id in connection_ids and edge.destination_id in producer_ids,
        }[edge.kind]
        if not valid:
            raise ConfigurationError(
                f"Resolved signal graph edge {edge.id!r} references an unknown node."
            )


def _callable_origin(value: Any, fallback: str) -> SourceOrigin:
    if value is None:
        return SourceOrigin("registry", fallback)
    module = getattr(value, "__module__", "<unknown>")
    qualname = getattr(value, "__qualname__", getattr(value, "__name__", fallback))
    try:
        _, line = inspect.getsourcelines(value)
    except TypeError, OSError:
        line = None
    return SourceOrigin("registry", f"{module}:{qualname}", line)


def _compile_producers(registry: Any | None) -> tuple[_SignalProducerNode, ...]:
    if registry is None:
        return ()
    primary_specs, derived_specs = registry._topology_specs()
    nodes = [
        _SignalProducerNode(
            id=stable_identity("signal_producer", spec.name),
            name=spec.name,
            kind="primary",
            source_kind="lazy" if spec.source is not None else "push",
            dependencies=(),
            audience=spec.audience,
            coalesce=spec.coalesce,
            origin=_callable_origin(spec.source or spec.initial or spec.render, spec.name),
        )
        for spec in primary_specs
    ]
    nodes.extend(
        _SignalProducerNode(
            id=stable_identity("signal_producer", spec.name),
            name=spec.name,
            kind="derived",
            source_kind="derived",
            dependencies=tuple(spec.deps),
            audience=spec.audience,
            coalesce=True,
            origin=_callable_origin(spec.compute, spec.name),
        )
        for spec in derived_specs
    )
    return tuple(sorted(nodes, key=lambda node: node.id))


def _source_line(source: str, start: int) -> int:
    return source.count("\n", 0, start) + 1


def _without_template_comments(source: str) -> str:
    return _TEMPLATE_COMMENT.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), source)


def _binding_facts(source: str) -> tuple[_BindingFact, ...]:
    source = _without_template_comments(source)
    facts: list[_BindingFact] = []
    literal_starts: set[int] = set()
    for match in _LITERAL_HELPER.finditer(source):
        literal_starts.add(match.start())
        facts.append(
            _BindingFact(
                match.group("name"), "helper", match.start(), _source_line(source, match.start())
            )
        )
    facts.extend(
        _BindingFact(None, "dynamic", match.start(), _source_line(source, match.start()))
        for match in _HELPER_CALL.finditer(source)
        if match.start() not in literal_starts
    )
    facts.extend(
        _BindingFact(
            match.group("name"), "marker", match.start(), _source_line(source, match.start())
        )
        for match in _RAW_BINDING.finditer(source)
    )
    return tuple(
        sorted(facts, key=lambda fact: (fact.start, fact.evidence, fact.signal_name or ""))
    )


def _connection_lines(source: str) -> tuple[int, ...]:
    source = _without_template_comments(source)
    starts = [match.start() for match in _HELPER_CONNECTION.finditer(source)]
    starts.extend(
        match.start()
        for match in _LITERAL_CONNECTION.finditer(source)
        if match.group("url").split("?", 1)[0].rstrip("/") == _SIGNAL_STREAM_PATH
    )
    return tuple(_source_line(source, start) for start in sorted(starts))


def _load_reachable_sources(program: HypermediaProgram, kida_env: Any | None) -> dict[str, str]:
    if kida_env is None or kida_env.loader is None:
        return {}
    sources: dict[str, str] = {}
    for template in program.templates:
        if template.load_error is not None:
            continue
        try:
            source, _ = kida_env.loader.get_source(template.name)
        except Exception:
            _logger.debug(
                "Reachable template source %r could not be loaded for signal compilation",
                template.name,
                exc_info=True,
            )
            continue
        sources[template.name] = source
    return sources


def _connection_owner(
    template_name: str,
    *,
    templates_by_name: dict[str, Any],
    connections_by_template: dict[str, tuple[_SignalConnectionNode, ...]],
    composition_chains: dict[str, tuple[tuple[str, ...], ...]],
) -> tuple[_SignalConnectionNode | None, _Ownership]:
    def resolve_path(path: tuple[str, ...]) -> tuple[_SignalConnectionNode | None, _Ownership]:
        visited: set[str] = set()
        pending = list(path)
        while pending:
            current = pending.pop(0)
            while current not in visited:
                visited.add(current)
                candidates = connections_by_template.get(current, ())
                if len(candidates) == 1:
                    return candidates[0], "resolved"
                if len(candidates) > 1:
                    return None, "ambiguous"
                template = templates_by_name.get(current)
                parent = template.extends if template is not None else None
                if parent is None:
                    break
                current = parent
        return None, "missing"

    paths = composition_chains.get(template_name)
    if paths is None:
        paths = ((template_name,),)
    results = tuple(resolve_path((template_name, *reversed(path))) for path in paths)
    owners = {owner.id: owner for owner, _status in results if owner is not None}
    statuses = {status for _owner, status in results}
    if len(owners) == 1 and statuses == {"resolved"}:
        return next(iter(owners.values())), "resolved"
    if owners or "ambiguous" in statuses:
        return None, "ambiguous"
    return None, "missing"


def _composition_chains(
    route_templates: dict[str, str],
    route_layout_chains: dict[str, Any],
) -> dict[str, tuple[tuple[str, ...], ...]]:
    by_template: dict[str, set[tuple[str, ...]]] = {}
    for path, template_name in sorted(route_templates.items()):
        chain = route_layout_chains.get(path)
        if chain is None:
            continue
        layout_names = tuple(layout.template_name for layout in chain.layouts)
        by_template.setdefault(template_name, set()).add(layout_names)
    return {template_name: tuple(sorted(chains)) for template_name, chains in by_template.items()}


def _edge(
    kind: _SignalEdgeKind,
    source_id: str,
    destination_id: str,
    *,
    resolved: bool,
    origin: SourceOrigin,
) -> _SignalEdge:
    return _SignalEdge(
        id=stable_identity("signal_edge", kind, source_id, destination_id),
        kind=kind,
        source_id=source_id,
        destination_id=destination_id,
        resolved=resolved,
        origin=origin,
    )


def compile_signal_graph(
    *,
    registry: Any | None,
    program: HypermediaProgram,
    kida_env: Any | None,
    route_templates: dict[str, str],
    route_layout_chains: dict[str, Any],
) -> _SignalGraph:
    """Compile registry declarations and reachable static template evidence."""
    producers = _compile_producers(registry)
    producer_ids = {node.name: node.id for node in producers}
    sources = _load_reachable_sources(program, kida_env)
    templates_by_name = {node.name: node for node in program.templates}
    composition_chains = _composition_chains(route_templates, route_layout_chains)

    connections: list[_SignalConnectionNode] = []
    connections_by_template: dict[str, tuple[_SignalConnectionNode, ...]] = {}
    for template_name in sorted(sources):
        template_connections = tuple(
            _SignalConnectionNode(
                id=stable_identity("signal_connection", template_name, str(index)),
                template_id=stable_identity("template", template_name),
                origin=SourceOrigin("template", template_name, line),
            )
            for index, line in enumerate(_connection_lines(sources[template_name]), start=1)
        )
        connections.extend(template_connections)
        connections_by_template[template_name] = template_connections

    bindings: list[_SignalBindingNode] = []
    owners: dict[str, _SignalConnectionNode] = {}
    for template_name in sorted(sources):
        owner, ownership = _connection_owner(
            template_name,
            templates_by_name=templates_by_name,
            connections_by_template=connections_by_template,
            composition_chains=composition_chains,
        )
        for index, fact in enumerate(_binding_facts(sources[template_name]), start=1):
            binding = _SignalBindingNode(
                id=stable_identity(
                    "signal_binding",
                    template_name,
                    str(index),
                    fact.signal_name or "<dynamic>",
                ),
                signal_name=fact.signal_name,
                template_id=stable_identity("template", template_name),
                evidence=fact.evidence,
                ownership=ownership,
                origin=SourceOrigin("template", template_name, fact.line),
            )
            bindings.append(binding)
            if owner is not None:
                owners[binding.id] = owner

    edges: list[_SignalEdge] = []
    edges.extend(
        _edge(
            "depends_on",
            producer_ids[dependency],
            producer.id,
            resolved=True,
            origin=producer.origin,
        )
        for producer in producers
        for dependency in producer.dependencies
    )

    producers_by_name = {node.name: node for node in producers}
    for binding in bindings:
        if binding.signal_name is not None:
            source_id = stable_identity("signal_producer", binding.signal_name)
            edges.append(
                _edge(
                    "renders_to",
                    source_id,
                    binding.id,
                    resolved=binding.signal_name in producers_by_name,
                    origin=binding.origin,
                )
            )
        owner = owners.get(binding.id)
        if owner is None:
            continue
        edges.append(
            _edge(
                "owned_by",
                binding.id,
                owner.id,
                resolved=True,
                origin=binding.origin,
            )
        )
        if binding.signal_name not in producers_by_name:
            continue
        pending = [binding.signal_name]
        activated: set[str] = set()
        while pending:
            name = pending.pop()
            if name in activated:
                continue
            activated.add(name)
            pending.extend(producers_by_name[name].dependencies)
        edges.extend(
            _edge(
                "activates",
                owner.id,
                producer_ids[name],
                resolved=True,
                origin=binding.origin,
            )
            for name in sorted(activated)
        )

    unique_edges = {edge.id: edge for edge in edges}
    return _SignalGraph(
        producers=producers,
        bindings=tuple(sorted(bindings, key=lambda node: node.id)),
        connections=tuple(sorted(connections, key=lambda node: node.id)),
        edges=tuple(sorted(unique_edges.values(), key=lambda edge: edge.id)),
    )

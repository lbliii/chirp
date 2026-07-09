"""Regression proof for the private Contract Explorer topology projection."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest
from kida import DictLoader, Environment

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import FragmentContract, check_hypermedia_surface, contract
from chirp.contracts.explorer_projection import (
    ExplorerNode,
    build_explorer_projection,
)
from chirp.contracts.types import CheckResult, ContractCoverage, ContractIssue, Severity


def _home() -> str:
    return "not executed"


def _events() -> str:
    return "not executed"


def _late() -> str:
    return "not executed"


def _app_with_topology(template_dir: Path, *, reverse: bool = False) -> App:
    template_dir.mkdir(exist_ok=True)
    (template_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}ok{% endblock %}{% endblock %}",
        encoding="utf-8",
    )
    app = App(
        AppConfig(
            template_dir=template_dir,
            debug=False,
            skip_contract_checks=True,
        )
    )
    registrations = [
        ("/", _home, "home"),
        ("/events", _events, "events"),
    ]
    if reverse:
        registrations.reverse()
    for path, handler, name in registrations:
        app.route(path, name=name, template="page.html")(handler)
    app._mutable_state.page_templates.add("page.html")
    app._mutable_state.page_leaf_templates.add("page.html")
    app._mutable_state.fragment_target_registry.register(
        "main",
        fragment_block="page_root",
        required=True,
        contract_name="application-shell",
    )
    return app


def _finalized_result() -> CheckResult:
    return CheckResult(
        issues=[
            ContractIssue(
                Severity.ERROR,
                "sse",
                "SSE fragment is malformed.",
                route="/events",
                template="page.html",
                details="Use an existing block.",
            ),
            ContractIssue(
                Severity.ERROR,
                "oob_registry",
                "OOB region is unbound.",
            ),
            ContractIssue(
                Severity.WARNING,
                "suspense_defer",
                "Suspense dependency is undiscoverable.",
                template="page.html",
            ),
        ],
        coverage=ContractCoverage(
            fragment_targets_registered=1,
            oob_regions_registered=1,
            page_shell_contracts=1,
            page_shell_required_blocks=1,
        ),
    )


def _node_attributes(node: ExplorerNode) -> dict[str, str]:
    return dict(node.attributes)


@pytest.mark.issue(652)
def test_projection_copies_compiler_topology_and_finalized_findings(tmp_path: Path) -> None:
    app = _app_with_topology(tmp_path)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None

    projection = build_explorer_projection(program, _finalized_result())

    assert {node.id for node in projection.nodes} == {
        *(node.id for node in program.routes),
        *(node.id for node in program.templates),
        *(node.id for node in program.blocks),
        *(node.id for node in program.targets),
    }
    assert {
        (edge.id, edge.kind, edge.source_id, edge.destination_id, edge.resolved)
        for edge in projection.edges
    } == {
        (edge.id, edge.kind, edge.source_id, edge.destination_id, edge.resolved)
        for edge in program.transitions
    }

    home = next(node for node in projection.nodes if node.kind == "route" and node.label == "GET /")
    assert _node_attributes(home)["name"] == "home"
    target = next(node for node in projection.nodes if node.kind == "target")
    assert _node_attributes(target) == {
        "contract_name": "application-shell",
        "fragment_block": "page_root",
        "required": "true",
        "target_id": "main",
    }

    findings = {finding.category: finding for finding in projection.findings}
    assert findings["sse"].binding == "bound"
    assert findings["sse"].route_node_ids
    assert findings["sse"].template_node_ids
    assert findings["sse"].details == "Use an existing block."
    assert findings["suspense_defer"].binding == "bound"
    assert findings["oob_registry"].binding == "unbound"
    assert dict(projection.coverage)["oob_regions_registered"] == 1
    assert "oob_topology:not_compiled" in projection.analysis_gaps
    assert "suspense_topology:not_compiled" in projection.analysis_gaps
    assert "sse_topology:not_compiled" in projection.analysis_gaps


@pytest.mark.issue(652)
def test_projection_includes_mounted_named_routes(tmp_path: Path) -> None:
    parent = _app_with_topology(tmp_path / "parent")
    child = App(AppConfig(debug=False, skip_contract_checks=True))
    child.route("/", name="admin.home")(_late)
    parent.mount_app("/admin", child)
    parent.freeze()
    program = parent._runtime_state.hypermedia_program
    assert program is not None

    projection = build_explorer_projection(program, CheckResult())

    mounted = next(
        node
        for node in projection.nodes
        if node.kind == "route" and _node_attributes(node)["path"] == "/admin"
    )
    assert mounted.label == "GET /admin"
    assert _node_attributes(mounted)["name"] == "admin.home"


@pytest.mark.issue(652)
def test_projection_keeps_unresolved_edges_and_malformed_locations_unbound(
    tmp_path: Path,
) -> None:
    app = App(AppConfig(template_dir=tmp_path, debug=False, skip_contract_checks=True))

    @app.route("/broken", methods=["GET", "POST"])
    @contract(returns=FragmentContract("missing.html", "missing_block"))
    def broken() -> str:
        return "not executed"

    result = check_hypermedia_surface(app)
    result.issues.extend(
        [
            ContractIssue(Severity.ERROR, "malformed", "No exact location."),
            ContractIssue(
                Severity.ERROR,
                "unknown_location",
                "Location is absent from compiled topology.",
                route="/not-registered",
                template="not-compiled.html",
            ),
            ContractIssue(
                Severity.WARNING,
                "method_ambiguous",
                "A path alone does not identify one method-specific route.",
                route="/broken",
            ),
        ]
    )
    program = app._runtime_state.hypermedia_program
    assert program is not None

    projection = build_explorer_projection(program, result)

    unresolved = [edge for edge in projection.edges if not edge.resolved]
    assert {edge.kind for edge in unresolved} == {"route_block", "route_template"}
    findings = {finding.category: finding for finding in projection.findings}
    assert findings["malformed"].binding == "unbound"
    assert findings["unknown_location"].binding == "unbound"
    assert findings["unknown_location"].route_node_ids == ()
    assert findings["unknown_location"].template_node_ids == ()
    assert findings["method_ambiguous"].binding == "ambiguous"
    assert len(findings["method_ambiguous"].route_node_ids) == 2


@pytest.mark.issue(652)
def test_missing_finalized_checks_are_unavailable_not_clean(tmp_path: Path) -> None:
    app = _app_with_topology(tmp_path)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None

    projection = build_explorer_projection(program, None)

    assert projection.findings == ()
    assert projection.coverage == ()
    assert "contract_findings_and_coverage:unavailable" in projection.analysis_gaps


@pytest.mark.issue(652)
def test_equivalent_apps_produce_byte_stable_projections(tmp_path: Path) -> None:
    first = _app_with_topology(tmp_path / "first", reverse=False)
    second = _app_with_topology(tmp_path / "second", reverse=True)
    first.freeze()
    second.freeze()
    first_program = first._runtime_state.hypermedia_program
    second_program = second._runtime_state.hypermedia_program
    assert first_program is not None
    assert second_program is not None

    first_projection = build_explorer_projection(first_program, _finalized_result())
    second_projection = build_explorer_projection(second_program, _finalized_result())
    first_bytes = json.dumps(
        asdict(first_projection), sort_keys=True, separators=(",", ":")
    ).encode()
    second_bytes = json.dumps(
        asdict(second_projection), sort_keys=True, separators=(",", ":")
    ).encode()

    assert first_bytes == second_bytes


def _attempt_mutation(value: object, attribute: str, replacement: object) -> None:
    setattr(value, attribute, replacement)


@pytest.mark.issue(652)
def test_projection_is_an_immutable_copy_of_finalized_checks(tmp_path: Path) -> None:
    app = _app_with_topology(tmp_path)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None
    result = _finalized_result()
    projection = build_explorer_projection(program, result)
    finding_count = len(projection.findings)

    result.issues.clear()

    assert len(projection.findings) == finding_count
    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(projection, "nodes", ())
    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(projection.nodes[0], "label", "late")


@pytest.mark.issue(652)
def test_concurrent_projection_builds_publish_complete_equal_snapshots(tmp_path: Path) -> None:
    app = _app_with_topology(tmp_path)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None
    result = _finalized_result()

    with ThreadPoolExecutor(max_workers=16) as pool:
        projections = list(
            pool.map(lambda _index: build_explorer_projection(program, result), range(80))
        )

    assert all(projection == projections[0] for projection in projections)
    assert all(projection.nodes for projection in projections)
    assert all(projection.edges for projection in projections)
    assert all(projection.findings for projection in projections)


class _CountingLoader(DictLoader):
    def __init__(self, mapping: dict[str, str]) -> None:
        super().__init__(mapping)
        self.source_reads = 0
        self.inventory_reads = 0

    def get_source(self, name: str) -> tuple[str, None]:
        self.source_reads += 1
        return super().get_source(name)

    def list_templates(self) -> list[str]:
        self.inventory_reads += 1
        return super().list_templates()


@pytest.mark.issue(652)
def test_projection_never_executes_routes_or_reads_templates() -> None:
    loader = _CountingLoader({"page.html": "{% block content %}ok{% endblock %}"})
    app = App(
        AppConfig(debug=False, skip_contract_checks=True),
        kida_env=Environment(loader=loader),
    )
    handler_calls = 0

    @app.route("/", template="page.html")
    def index() -> str:
        nonlocal handler_calls
        handler_calls += 1
        return "executed"

    result = check_hypermedia_surface(app)
    program = app._runtime_state.hypermedia_program
    assert program is not None
    reads_after_authoritative_compiler_and_check = (
        loader.source_reads,
        loader.inventory_reads,
    )

    for _ in range(20):
        build_explorer_projection(program, result)

    assert handler_calls == 0
    assert (
        loader.source_reads,
        loader.inventory_reads,
    ) == reads_after_authoritative_compiler_and_check

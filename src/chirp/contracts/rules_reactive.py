"""Reactive bus contract checks.

Validates DependencyIndex configuration at app.check() time:
- Block references point to real template blocks
- Derivation graph is a DAG (no cycles)
- Declared emitted paths are registered in the dependency index
- Audience-filtered scopes have connection-aware subscribers
"""

from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida import Environment

    from chirp.pages.reactive.index import DependencyIndex


def check_reactive_block_existence(
    dep_index: DependencyIndex,
    env: Environment,
) -> list[ContractIssue]:
    """Verify every BlockRef in the index references a real template block."""
    issues: list[ContractIssue] = []
    checked: set[tuple[str, str]] = set()

    for refs in dep_index._path_to_blocks.values():
        for ref in refs:
            key = (ref.template_name, ref.block_name)
            if key in checked:
                continue
            checked.add(key)
            try:
                template = env.get_template(ref.template_name)
                blocks = template.block_metadata()
                if ref.block_name not in blocks:
                    issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="reactive_block",
                            message=(
                                f"DependencyIndex references block '{ref.block_name}' "
                                f"in template '{ref.template_name}', but no such block exists. "
                                f"Available: {', '.join(sorted(blocks)) or '(none)'}."
                            ),
                            template=ref.template_name,
                        )
                    )
            except Exception:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="reactive_block",
                        message=(
                            f"DependencyIndex references template '{ref.template_name}' "
                            "which could not be loaded."
                        ),
                        template=ref.template_name,
                    )
                )
    return issues


def check_reactive_derivation_dag(
    dep_index: DependencyIndex,
) -> list[ContractIssue]:
    """Detect cycles in the derivation graph.

    Cycles are handled safely at runtime (BFS visited set), but always
    indicate a configuration error.  Surfacing at check time is better
    than silent infinite-expansion prevention at runtime.
    """
    issues: list[ContractIssue] = []
    graph = dep_index._source_to_derived

    if not graph:
        return issues

    # Collect all nodes
    white, gray, black = 0, 1, 2
    color: dict[str, int] = {}
    for source, targets in graph.items():
        color.setdefault(source, white)
        for t in targets:
            color.setdefault(t, white)

    reported_cycles: set[frozenset[str]] = set()

    def dfs(node: str, path: list[str]) -> None:
        color[node] = gray
        path.append(node)
        for neighbor in graph.get(node, []):
            if color.get(neighbor, white) == gray:
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                cycle_key = frozenset(cycle)
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="reactive_cycle",
                            message=(
                                f"Derivation cycle detected: {' -> '.join(cycle)}. "
                                "Cycles are handled safely at runtime but indicate "
                                "a configuration error."
                            ),
                        )
                    )
            elif color.get(neighbor, white) == white:
                dfs(neighbor, path)
        path.pop()
        color[node] = black

    for node in list(color):
        if color[node] == white:
            dfs(node, [])

    return issues


def check_reactive_emitted_paths(
    dep_index: DependencyIndex,
    emitted_paths: object,
) -> list[ContractIssue]:
    """Warn when declared ChangeEvent paths are not registered in the index."""
    if emitted_paths is None:
        return []
    if isinstance(emitted_paths, str):
        paths = {emitted_paths}
    else:
        try:
            paths = set(emitted_paths)
        except TypeError:
            return [
                ContractIssue(
                    severity=Severity.WARNING,
                    category="reactive_paths",
                    message=(
                        "reactive_emitted_paths contract data must be an iterable "
                        "of path strings."
                    ),
                )
            ]

    registered = set(dep_index._path_to_blocks)
    missing = sorted(path for path in paths if isinstance(path, str) and path not in registered)
    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="reactive_paths",
            message=(
                f"Reactive ChangeEvent path '{path}' is declared as emitted but "
                "is not registered in the DependencyIndex. Register the path or "
                "remove it from app.set_contract_check_data('reactive_emitted_paths', ...)."
            ),
        )
        for path in missing
    ]


def check_reactive_audience_scopes(
    audience_scopes: object,
    connection_scopes: object,
) -> list[ContractIssue]:
    """Warn when audience-filtered events target scopes without ConnectionInfo."""
    if audience_scopes is None:
        return []

    try:
        audiences = set(audience_scopes) if not isinstance(audience_scopes, str) else {audience_scopes}
        connections = (
            set(connection_scopes)
            if connection_scopes is not None and not isinstance(connection_scopes, str)
            else ({connection_scopes} if isinstance(connection_scopes, str) else set())
        )
    except TypeError:
        return [
            ContractIssue(
                severity=Severity.WARNING,
                category="reactive_audience",
                message=(
                    "reactive_audience_scopes and reactive_connection_scopes "
                    "contract data must be iterables of scope strings."
                ),
            )
        ]

    missing = sorted(scope for scope in audiences if isinstance(scope, str) and scope not in connections)
    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="reactive_audience",
            message=(
                f"Reactive scope '{scope}' declares audience-filtered events but "
                "no connection-aware reactive_stream. Pass ConnectionInfo to "
                "reactive_stream(..., connection=...) for that scope."
            ),
        )
        for scope in missing
    ]

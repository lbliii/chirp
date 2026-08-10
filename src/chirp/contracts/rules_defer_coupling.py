"""Suspense defer coupling contract (#949).

Uses the freeze-time Suspense defer execution DAG (#948) to warn when deferred
context keys share a leaf block (``couples`` edges). Coupled keys are not
independent for concurrent resolution / distinct pool checkouts — they wait on
the same OOB leaf. Split them into separate leaf blocks when independence
matters; keep a shared panel only when serial resolution is intentional.

Severity is env-aware: **silent in development**, ``WARNING`` in staging and
production. Never ``ERROR`` by default — shared-panel coupling is a valid
hypermedia pattern and must not fail production boots without evidence. Promote
via ``app.override_contract_severity("defer_coupling", Severity.ERROR)`` in CI
when independence is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app._suspense_dag import _SuspenseDeferDAG


def _env_severity(env: str) -> Severity | None:
    """Return env-aware severity, or ``None`` to stay silent (development)."""
    if env not in ("production", "staging"):
        return None
    return Severity.WARNING


def _shared_blocks(plan: Any, left: str, right: str) -> tuple[str, ...]:
    key_blocks = plan.plan.key_blocks
    return tuple(sorted(set(key_blocks.get(left, ())) & set(key_blocks.get(right, ()))))


def check_defer_coupling(
    dag: _SuspenseDeferDAG | None,
    *,
    env: str = "development",
) -> list[ContractIssue]:
    """Flag Suspense routes whose deferred keys share a leaf block.

    Reads ``couples`` edges from the compiled freeze-time DAG. One ``WARNING``
    (staging/production) per unordered key pair. Independent keys (no
    ``couples`` edges) are silent.
    """
    severity = _env_severity(env)
    if severity is None or dag is None:
        return []

    issues: list[ContractIssue] = []
    for route_plan in dag.routes:
        for left, right in sorted(route_plan.coupled_key_pairs()):
            shared = _shared_blocks(route_plan, left, right)
            if shared:
                shared_txt = ", ".join(f"'{block}'" for block in shared)
                consequence = f"share leaf block(s) {shared_txt}"
            else:
                consequence = "are coupled through a shared leaf block"
            explicit = (
                " This plan used Suspense(..., defer_blocks=...), which feeds every"
                " deferred key into every listed block and therefore couples them."
                if route_plan.plan.explicit_blocks
                else ""
            )
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="defer_coupling",
                    message=(
                        f"Suspense route '{route_plan.method} {route_plan.path}' "
                        f"(template '{route_plan.template_name}') couples deferred "
                        f"keys '{left}' and '{right}' — they {consequence}, so they "
                        "cannot resolve independently for concurrent checkout / "
                        "distinct pool connections."
                        f"{explicit} Split the keys into separate leaf blocks when "
                        "independence matters, or keep the shared panel and accept "
                        "serial resolution."
                    ),
                    route=route_plan.path,
                    template=route_plan.template_name,
                )
            )
    return issues

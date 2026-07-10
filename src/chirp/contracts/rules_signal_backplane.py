"""Deployment-safety contract for the private signal backplane."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.config import AppConfig
    from chirp.realtime.signal_backplane import _SignalBackplaneDescriptor


_DETAILS = (
    "Set AppConfig(workers=1), or configure AppConfig(redis_url=...) / "
    "CHIRP_REDIS_URL for the private Redis signal backplane and keep signal "
    "source state in a shared store before deploying."
)


def check_signal_bus_single_worker(
    config: AppConfig,
    descriptor: _SignalBackplaneDescriptor | None,
    signal_names: frozenset[str],
    *,
    workers: int | None = None,
) -> list[ContractIssue]:
    """Flag process-local signals under an effective multi-worker posture."""
    if not signal_names or descriptor is None or not descriptor.process_local:
        return []
    effective_workers = config.workers if workers is None else workers
    if effective_workers == 1:
        return []

    severity: Severity | None = None
    if config.env == "production" and (effective_workers == 0 or effective_workers > 1):
        severity = Severity.ERROR
    elif (config.env == "staging" and (effective_workers == 0 or effective_workers > 1)) or (
        config.env == "development" and effective_workers > 1
    ):
        severity = Severity.WARNING
    if severity is None:
        return []

    rendered_workers = "0 (auto)" if effective_workers == 0 else str(effective_workers)
    return [
        ContractIssue(
            severity=severity,
            category="signal_bus_single_worker",
            message=(
                f"Signals use a process-local bus with workers={rendered_workers}; "
                "realtime updates cannot reach clients connected to another worker."
            ),
            details=_DETAILS,
        )
    ]

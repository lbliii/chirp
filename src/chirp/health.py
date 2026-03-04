"""Health probes for Kubernetes and load balancers.

Provides liveness and readiness endpoints for container orchestration.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A single readiness check."""

    name: str
    check: Callable[[], bool | Any]  # sync; return True if healthy
    message: str = ""


def liveness() -> bool:
    """Liveness probe — is the process alive?

    Returns True. Use for K8s livenessProbe. If this fails, the pod
    is restarted.
    """
    return True


def readiness(checks: list[HealthCheck]) -> tuple[bool, list[str]]:
    """Readiness probe — is the app ready to receive traffic?

    Runs each check. Returns (all_ok, list of failure messages).
    Use for K8s readinessProbe. If not ready, the pod is removed
    from service endpoints.
    """
    failures: list[str] = []
    for hc in checks:
        try:
            result = hc.check()
            if result is not True:
                failures.append(hc.message or f"{hc.name}: unhealthy")
        except Exception as e:
            failures.append(f"{hc.name}: {e!s}")
    return (len(failures) == 0, failures)

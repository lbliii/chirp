"""Health probes for Kubernetes and load balancers.

Provides liveness and readiness endpoints for container orchestration.

Chirp auto-mounts ``/health`` (liveness) and ``/ready`` (readiness) at the paths
in :class:`~chirp.config.AppConfig` (``health_path`` / ``ready_path``) unless a
user route already claims them. ``/health`` always returns ``200`` — it answers
"is the process alive?" (K8s ``livenessProbe``). ``/ready`` runs every registered
:class:`HealthCheck` *and* gates on the startup-complete flag, returning ``503``
plus the failure list until the app has finished startup and all checks pass (K8s
``readinessProbe``).

Register readiness checks before freeze with ``app.add_health_check(...)``::

    from chirp import HealthCheck

    app.add_health_check(HealthCheck("cache", check=ping_cache))

When a database is wired, Chirp auto-includes a ``Database.probe()``-backed check
so ``/ready`` reflects DB connectivity with no hand-wiring. Probe checks may be
sync or async — ``readiness()`` awaits awaitable results.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import isawaitable


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A single readiness check.

    ``check`` is a zero-argument callable returning truthy when healthy. It may
    be sync (``() -> bool``) or async (``() -> Awaitable[bool]``); ``readiness()``
    awaits awaitable results. ``message`` is the failure message surfaced on
    ``/ready`` when the check is unhealthy or raises.
    """

    name: str
    check: Callable[[], Awaitable[bool] | bool]  # return truthy if healthy
    message: str = ""


def liveness() -> bool:
    """Liveness probe — is the process alive?

    Returns True. Use for K8s livenessProbe. If this fails, the pod
    is restarted.
    """
    return True


async def readiness(checks: list[HealthCheck]) -> tuple[bool, list[str]]:
    """Readiness probe — is the app ready to receive traffic?

    Runs each check (awaiting awaitable results) and returns
    ``(all_ok, list of failure messages)``. Use for K8s readinessProbe. If not
    ready, the pod is removed from service endpoints.

    This is ``async`` so checks can express async DB/Redis pings; sync checks are
    supported transparently (only awaitable results are awaited).
    """
    failures: list[str] = []
    for hc in checks:
        try:
            result = hc.check()
            if isawaitable(result):
                result = await result
            if result is not True:
                failures.append(hc.message or f"{hc.name}: unhealthy")
        except Exception as e:
            failures.append(f"{hc.name}: {e!s}")
    return (len(failures) == 0, failures)

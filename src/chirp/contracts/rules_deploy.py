"""Deploy-preflight contract checks — production misconfiguration, fail loud.

These complement the existing safety rules (secret_key, allowed_hosts) with the
production-posture mistakes that otherwise surface only after deploy:

- ``deploy_debug``: ``debug=True`` while ``env="production"``
- ``deploy_metrics``: ``metrics_path`` collides with an application route
- ``deploy_sentry``: a Sentry DSN is set but traces are silently disabled

Scope is strictly *check rules* — no deploy automation, no Procfile/Dockerfile
generation, no in-core APM. Prometheus/Sentry/OTel stay config-surface
integrations; these rules only catch their silent misconfiguration.
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router


def check_debug_in_production(config: Any) -> list[ContractIssue]:
    """ERROR when ``debug=True`` in a production environment.

    Debug mode enables verbose error pages (information disclosure), hot
    reload, and dev tooling — never appropriate in production.
    """
    env = getattr(config, "env", "development")
    if env == "production" and getattr(config, "debug", False):
        return [
            ContractIssue(
                severity=Severity.ERROR,
                category="deploy_debug",
                message=(
                    "debug=True while env='production'. Debug mode exposes "
                    "tracebacks and enables hot reload — set debug=False (or "
                    "CHIRP_DEBUG=0) before deploying to production."
                ),
            )
        ]
    return []


def check_metrics_path_collision(config: Any, router: Router) -> list[ContractIssue]:
    """ERROR when the Prometheus ``metrics_path`` collides with an app route.

    When metrics are enabled, the metrics endpoint and an application route
    sharing a path silently shadow each other — one of them never serves.

    Scope: this sees metrics configured via ``AppConfig.metrics_enabled`` /
    ``metrics_path`` only. Metrics enabled solely through
    ``run_production_server(metrics_enabled=...)`` arguments are not visible at
    ``app.check()`` time and are not covered here.
    """
    if not getattr(config, "metrics_enabled", False):
        return []
    metrics_path = getattr(config, "metrics_path", "/metrics")
    for route in getattr(router, "routes", []):
        if getattr(route, "path", None) == metrics_path:
            return [
                ContractIssue(
                    severity=Severity.ERROR,
                    category="deploy_metrics",
                    message=(
                        f"metrics_path '{metrics_path}' collides with the "
                        f"application route '{route.path}'. The Prometheus "
                        f"endpoint and the route shadow each other — change "
                        f"metrics_path or move the route."
                    ),
                    route=metrics_path,
                )
            ]
    return []


def check_sentry_sample_rate(config: Any) -> list[ContractIssue]:
    """WARN when a Sentry DSN is configured but tracing is disabled.

    A DSN with ``sentry_traces_sample_rate == 0`` captures errors but no
    performance traces — usually an oversight when observability is wanted.
    """
    dsn = getattr(config, "sentry_dsn", None)
    rate = getattr(config, "sentry_traces_sample_rate", 0.1)
    if dsn and rate == 0:
        return [
            ContractIssue(
                severity=Severity.WARNING,
                category="deploy_sentry",
                message=(
                    "sentry_dsn is set but sentry_traces_sample_rate is 0 — "
                    "performance traces are disabled. Set a non-zero sample "
                    "rate (e.g. 0.1) or clear the DSN if tracing is intentional."
                ),
            )
        ]
    return []

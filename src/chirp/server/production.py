"""Production server with pounce Phase 5 & 6 features.

Starts a pounce production server with multi-worker, metrics, rate limiting,
request queueing, error tracking, and zero-downtime hot reload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pounce import ASGIApp
from pounce.sync_protocol import SyncApp

if TYPE_CHECKING:
    from pounce.server import LifecycleCollector

    from chirp.app import App


def run_production_server(
    app: App,
    host: str = "0.0.0.0",
    port: int = 8000,
    workers: int = 0,  # 0 = auto-detect from CPU count
    worker_mode: str = "auto",  # "auto" | "sync" | "async" | "subinterpreter"
    *,
    # Phase 6.1: Prometheus Metrics
    metrics_enabled: bool = True,
    metrics_path: str = "/metrics",
    # Phase 6.2: Rate Limiting
    rate_limit_enabled: bool = False,
    rate_limit_requests_per_second: float = 100.0,
    rate_limit_burst: int = 200,
    rate_limit_max_tracked_ips: int = 100_000,
    # Proxy / forwarded headers
    trusted_proxies: tuple[str, ...] = (),
    forwarded_for_trusted_hops: int = 1,
    # Phase 6.3: Request Queueing
    request_queue_enabled: bool = False,
    request_queue_max_depth: int = 1000,
    # Phase 6.4: Sentry Error Tracking
    sentry_dsn: str | None = None,
    sentry_environment: str | None = None,
    sentry_release: str | None = None,
    sentry_traces_sample_rate: float = 0.1,
    # Phase 6.5: Hot Reload
    reload_timeout: float = 30.0,
    # Phase 5: OpenTelemetry
    otel_endpoint: str | None = None,
    otel_service_name: str = "chirp-app",
    # Phase 5: WebSocket
    websocket_compression: bool = True,
    websocket_max_message_size: int = 10_485_760,  # 10 MB
    # Production settings
    lifecycle_logging: bool = True,
    log_format: str = "auto",
    log_level: str = "info",
    max_connections: int = 1000,
    backlog: int = 2048,
    keep_alive_timeout: float = 5.0,
    request_timeout: float = 30.0,
    # TLS (optional)
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
    lifecycle_collector: LifecycleCollector | None = None,
) -> None:
    """Run chirp app in production mode with pounce Phase 5 & 6 features.

    Args:
        app: Chirp App instance.
        host: Bind address (default: 0.0.0.0 for all interfaces).
        port: Bind port (default: 8000).
        workers: Worker count (0 = auto-detect from CPU count).

        metrics_enabled: Enable Prometheus /metrics endpoint.
        metrics_path: Path for metrics endpoint (default: /metrics).

        rate_limit_enabled: Enable per-IP rate limiting.
        rate_limit_requests_per_second: Sustained rate limit per IP.
        rate_limit_burst: Maximum burst capacity per IP.
        rate_limit_max_tracked_ips: Max distinct client IPs the per-IP rate
            limiter tracks before LRU eviction (limiter memory cap).
        trusted_proxies: Reverse-proxy peer IPs/hostnames whose X-Forwarded-For
            is honored (mapped to pounce ServerConfig.trusted_hosts). Empty (the
            default) means X-Forwarded-For is ignored entirely; "*" trusts every
            direct peer (spoofing risk — use only on a locked-down network).
        forwarded_for_trusted_hops: Trailing X-Forwarded-For hops to trust
            when deriving the client IP behind a reverse proxy. Must be >= 1
            and only takes effect when trusted_proxies is non-empty (the direct
            peer must be a trusted proxy); to ignore X-Forwarded-For, leave
            trusted_proxies empty rather than setting this to 0.

        request_queue_enabled: Enable request queueing.
        request_queue_max_depth: Maximum queued requests (0 = unlimited).

        sentry_dsn: Sentry DSN for error tracking (None = disabled).
        sentry_environment: Sentry environment name (e.g., "production").
        sentry_release: Release version for Sentry (e.g., "myapp@1.0.0").
        sentry_traces_sample_rate: Performance monitoring sample rate (0.0-1.0).

        reload_timeout: Time to wait for workers to drain during hot reload.

        otel_endpoint: OpenTelemetry OTLP endpoint (None = disabled).
        otel_service_name: Service name for OpenTelemetry traces.

        websocket_compression: Enable WebSocket permessage-deflate compression.
        websocket_max_message_size: Maximum WebSocket message size (bytes).

        lifecycle_logging: Enable structured lifecycle event logging.
        log_format: Pounce log format — "auto" (TTY pretty / piped JSON),
            "text", or "json".
        log_level: Log level (debug, info, warning, error, critical).

        max_connections: Maximum concurrent connections.
        backlog: TCP listen backlog.
        keep_alive_timeout: Keep-alive connection timeout (seconds).
        request_timeout: Individual request timeout (seconds).

        ssl_certfile: Path to TLS certificate file (enables HTTPS/HTTP2).
        ssl_keyfile: Path to TLS private key file.
        lifecycle_collector: Optional Pounce lifecycle collector for
            startup/shutdown/worker hook event capture.

    Example:
        >>> from myapp import app
        >>> from chirp.server.production import run_production_server
        >>> run_production_server(
        ...     app,
        ...     workers=4,
        ...     metrics_enabled=True,
        ...     rate_limit_enabled=True,
        ...     sentry_dsn="https://...",
        ... )

    Environment Variables:
        You can also configure via environment variables:

        - WORKERS: Worker count
        - METRICS_ENABLED: Enable metrics (true/false)
        - RATE_LIMIT_ENABLED: Enable rate limiting (true/false)
        - SENTRY_DSN: Sentry DSN
        - OTEL_ENDPOINT: OpenTelemetry endpoint

    """
    if worker_mode == "subinterpreter":
        from chirp.errors import ConfigurationError

        msg = (
            "worker_mode='subinterpreter' requires a Pounce app import path, "
            "but Chirp production launch currently passes a live App object. "
            "Use worker_mode='sync', 'async', or 'auto' until Chirp supports "
            "import-string production launch."
        )
        raise ConfigurationError(msg)
    from pounce.config import ServerConfig
    from pounce.server import Server

    # Build pounce configuration
    config = ServerConfig(
        host=host,
        port=port,
        workers=workers,
        worker_mode=worker_mode,
        worker_startup_failure=(
            "shutdown" if app._worker_startup_hooks or app._worker_shutdown_hooks else "ignore"
        ),
        # Phase 6.1: Prometheus Metrics
        metrics_enabled=metrics_enabled,
        metrics_path=metrics_path,
        # Phase 6.2: Rate Limiting
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_requests_per_second=rate_limit_requests_per_second,
        rate_limit_burst=rate_limit_burst,
        rate_limit_max_tracked_ips=rate_limit_max_tracked_ips,
        # Proxy / forwarded headers
        # Pass trusted_hosts as a frozenset to match the declared field type;
        # pounce derives trusted_hosts_wildcard from it ("*" membership) — do
        # NOT set trusted_hosts_wildcard here.
        trusted_hosts=frozenset(trusted_proxies),
        forwarded_for_trusted_hops=forwarded_for_trusted_hops,
        # Phase 6.3: Request Queueing
        request_queue_enabled=request_queue_enabled,
        request_queue_max_depth=request_queue_max_depth,
        # Phase 6.4: Sentry Error Tracking
        sentry_dsn=sentry_dsn,
        sentry_environment=sentry_environment,
        sentry_release=sentry_release,
        sentry_traces_sample_rate=sentry_traces_sample_rate,
        # Phase 6.5: Hot Reload
        reload_timeout=reload_timeout,
        # Phase 5: OpenTelemetry
        otel_endpoint=otel_endpoint,
        otel_service_name=otel_service_name,
        # Phase 5: WebSocket
        websocket_compression=websocket_compression,
        websocket_max_message_size=websocket_max_message_size,
        # Production settings
        lifecycle_logging=lifecycle_logging,
        log_format=log_format,
        log_level=log_level,
        max_connections=max_connections,
        backlog=backlog,
        keep_alive_timeout=keep_alive_timeout,
        request_timeout=request_timeout,
        # Keep the wire-level Pounce ceiling aligned with Chirp's documented
        # application envelope. Otherwise Pounce's 1 MiB default rejects valid
        # Chirp requests before Request.body() can enforce the configured cap.
        max_request_size=app.config.max_request_body_size,
        # TLS
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        # Use pounce's built-in health check if chirp app doesn't define /health
        health_check_path=None,  # Let chirp app handle health checks
    )

    # Create and run server — pass app as sync_app for fused sync path
    server = Server(
        config,
        cast(ASGIApp, app),
        sync_app=cast(SyncApp, app),
        lifecycle_collector=lifecycle_collector,
    )
    server.run()

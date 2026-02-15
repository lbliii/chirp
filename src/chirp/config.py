"""Application configuration.

AppConfig is a frozen dataclass — immutable after creation, IDE-autocompletable,
no string-key dict lookups.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration. Immutable after creation.

    All fields have sensible defaults. Override what you need::

        config = AppConfig(debug=True, port=3000, secret_key="s3cr3t")
    """

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # Reload (development mode — requires debug=True)
    reload_include: tuple[str, ...] = ()  # Extra extensions to watch (e.g. ".html", ".css")
    reload_dirs: tuple[str, ...] = ()  # Extra directories to watch alongside cwd

    # Security
    secret_key: str = ""

    # Templates
    template_dir: str | Path = "templates"
    component_dirs: tuple[str | Path, ...] = ()  # Additional template directories (e.g. components, partials)
    autoescape: bool = True
    trim_blocks: bool = True
    lstrip_blocks: bool = True

    # Static files
    static_dir: str | Path | None = "static"
    static_url: str = "/static"

    # SSE
    sse_heartbeat_interval: float = 15.0
    sse_retry_ms: int | None = None
    sse_close_event: str | None = None

    # MCP (Model Context Protocol)
    mcp_path: str = "/mcp"

    # htmx safe target — auto-add hx-target="this" to event-driven elements
    safe_target: bool = True

    # SSE lifecycle — data-sse-state attribute + chirp:sse:connected/disconnected events
    sse_lifecycle: bool = True

    # View Transitions — auto-inject meta tag, default CSS, and htmx global config
    view_transitions: bool = False

    # Event delegation — copy-btn and compare-switch for SSE-swapped content
    delegation: bool = False

    # Alpine.js — local UI state (dropdowns, modals, tabs)
    alpine: bool = False
    alpine_version: str = "3.15.8"  # Pinned for reproducibility
    alpine_csp: bool = False  # Use CSP-safe build when True

    # Limits
    max_content_length: int = 16 * 1024 * 1024  # 16 MB

    # Production (pounce Phase 6 features)
    workers: int = 0  # 0 = auto-detect from CPU count (multi-worker for production)

    # Phase 6.1: Prometheus Metrics
    metrics_enabled: bool = False
    metrics_path: str = "/metrics"

    # Phase 6.2: Rate Limiting
    rate_limit_enabled: bool = False
    rate_limit_requests_per_second: float = 100.0
    rate_limit_burst: int = 200

    # Phase 6.3: Request Queueing
    request_queue_enabled: bool = False
    request_queue_max_depth: int = 1000

    # Phase 6.4: Sentry Error Tracking
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_release: str | None = None
    sentry_traces_sample_rate: float = 0.1

    # Phase 6.5: Hot Reload
    reload_timeout: float = 30.0

    # Phase 5: OpenTelemetry
    otel_endpoint: str | None = None
    otel_service_name: str = "chirp-app"

    # Phase 5: WebSocket
    websocket_compression: bool = True
    websocket_max_message_size: int = 10_485_760  # 10 MB

    # Production settings
    lifecycle_logging: bool = True
    log_format: str = "json"
    log_level: str = "info"
    max_connections: int = 1000
    backlog: int = 2048
    keep_alive_timeout: float = 5.0
    request_timeout: float = 30.0

    # TLS (optional)
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

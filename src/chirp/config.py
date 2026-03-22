"""Application configuration.

AppConfig is a frozen dataclass — immutable after creation, IDE-autocompletable,
no string-key dict lookups.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    return val in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_log_format(key: str, default: str) -> str:
    """Read log format from env; invalid values fall back to default."""
    val = (os.environ.get(key) or "").lower().strip()
    if val in ("auto", "text", "json"):
        return val
    return default


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
    # Default: web assets. API-only apps use reload_include=() to opt out.
    reload_include: tuple[str, ...] = (".html", ".css", ".md")
    reload_dirs: tuple[str, ...] = ()  # Extra directories to watch alongside cwd

    # Security
    secret_key: str = ""

    # Templates
    template_dir: str | Path = "templates"
    component_dirs: tuple[
        str | Path, ...
    ] = ()  # Additional template directories (e.g. components, partials)
    extra_loaders: tuple[Any, ...] = ()  # Kida Loader instances, tried first (CMS, DB, state)
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

    # Islands runtime — framework-agnostic high-state mount lifecycle
    islands: bool = False
    islands_version: str = "1"
    islands_contract_strict: bool = False  # Validate mount metadata in app.check()

    # Limits
    max_content_length: int = 16 * 1024 * 1024  # 16 MB

    # Production (pounce Phase 6 features)
    workers: int = 0  # 0 = auto-detect from CPU count (multi-worker for production)
    # Pounce worker execution: "auto" | "sync" | "async"
    # sync = blocking I/O, no asyncio; async = event loop; auto = sync on 3.14t, async on GIL
    worker_mode: str = "auto"

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
    # Pounce: "auto" = compact colored lines on a TTY, JSON when piped (same as pounce CLI)
    log_format: str = "auto"
    log_level: str = "info"
    max_connections: int = 1000
    backlog: int = 2048
    keep_alive_timeout: float = 5.0
    request_timeout: float = 30.0

    # TLS (optional)
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

    # Enterprise scale (12-factor, observability, shared state)
    env: str = "development"  # development | staging | production
    redis_url: str | None = None
    audit_sink: str | None = "log"  # "log" | "none" | custom
    feature_flags: tuple[tuple[str, bool], ...] = ()  # (name, value) pairs
    http_timeout: float = 30.0
    http_retries: int = 0
    skip_contract_checks: bool = False
    lazy_pages: bool = False

    @classmethod
    def from_env(cls, prefix: str = "CHIRP_") -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with the given prefix (default ``CHIRP_``).
        Unset vars use AppConfig defaults.

        If ``python-dotenv`` is installed (``pip install chirp[config]``),
        loads ``.env`` from the current directory before reading env.

        Env vars (with CHIRP_ prefix):
            SECRET_KEY, DEBUG, ENV, HOST, PORT,
            LOG_FORMAT (auto|text|json — forwarded to Pounce),
            SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE,
            REDIS_URL, AUDIT_SINK, SKIP_CONTRACT_CHECKS, LAZY_PAGES,
            HTTP_TIMEOUT, HTTP_RETRIES,
            FEATURE_<NAME>=true|false (e.g. CHIRP_FEATURE_X=true)
        """
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        p = prefix
        debug = _env_bool(f"{p}DEBUG", False)
        env_val = os.environ.get(f"{p}ENV", "development")
        feature_flags: list[tuple[str, bool]] = []
        for k, v in os.environ.items():
            if k.startswith(f"{p}FEATURE_") and len(k) > len(f"{p}FEATURE_"):
                name = k[len(f"{p}FEATURE_") :].lower().replace("_", "-")
                feature_flags.append((name, (v or "").lower() in ("1", "true", "yes", "on")))

        return cls(
            host=os.environ.get(f"{p}HOST", "127.0.0.1"),
            port=_env_int(f"{p}PORT", 8000),
            log_format=_env_log_format(f"{p}LOG_FORMAT", "auto"),
            debug=debug,
            secret_key=os.environ.get(f"{p}SECRET_KEY", ""),
            env=env_val,
            redis_url=os.environ.get(f"{p}REDIS_URL") or None,
            audit_sink=os.environ.get(f"{p}AUDIT_SINK", "log") or None,
            feature_flags=tuple(feature_flags),
            http_timeout=_env_float(f"{p}HTTP_TIMEOUT", 30.0),
            http_retries=_env_int(f"{p}HTTP_RETRIES", 0),
            skip_contract_checks=_env_bool(f"{p}SKIP_CONTRACT_CHECKS", False),
            lazy_pages=_env_bool(f"{p}LAZY_PAGES", False),
            sentry_dsn=os.environ.get(f"{p}SENTRY_DSN") or None,
            sentry_environment=os.environ.get(f"{p}SENTRY_ENVIRONMENT") or None,
            sentry_release=os.environ.get(f"{p}SENTRY_RELEASE") or None,
        )

    def feature(self, name: str) -> bool:
        """Return True if the named feature flag is enabled."""
        for k, v in self.feature_flags:
            if k == name:
                return v
        return False

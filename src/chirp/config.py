"""Application configuration.

AppConfig is a frozen dataclass — immutable after creation, IDE-autocompletable,
no string-key dict lookups.
"""

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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


def _env_int_first(keys: tuple[str, ...], default: int) -> int:
    """Read the first present integer env var from *keys*."""
    for key in keys:
        if key in os.environ:
            return _env_int(key, default)
    return default


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_allowed_hosts(prefix: str) -> tuple[str, ...]:
    """Read allowed hosts, with Railway healthcheck support when detectable."""
    raw = os.environ.get(f"{prefix}ALLOWED_HOSTS")
    if raw:
        hosts = tuple(part.strip() for part in raw.replace(",", " ").split() if part.strip())
        return hosts or ("*",)
    railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_public_domain:
        return (railway_public_domain, "healthcheck.railway.app")
    return ("*",)


def _env_log_format(key: str, default: str) -> str:
    """Read log format from env; invalid values fall back to default."""
    val = (os.environ.get(key) or "").lower().strip()
    if val in ("auto", "text", "json"):
        return val
    return default


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def _warn_unknown_env_vars(prefix: str, known_suffixes: frozenset[str]) -> None:
    """Emit warnings for unrecognized env vars with the given prefix."""
    feature_prefix = f"{prefix}FEATURE_"
    for key in os.environ:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix) :]
        if suffix in known_suffixes or key.startswith(feature_prefix):
            continue
        # Find closest known suffix by edit distance (sorted for determinism)
        best, best_dist = "", 999
        for candidate in sorted(known_suffixes):
            d = _levenshtein(suffix, candidate)
            if d < best_dist or (d == best_dist and candidate < best):
                best, best_dist = candidate, d
        hint = f" (did you mean {prefix}{best}?)" if best_dist <= 2 else ""
        warnings.warn(
            f"Unknown env var {key}{hint}. "
            f"Chirp reads: {prefix}<SUFFIX> where SUFFIX is one of: "
            + ", ".join(sorted(known_suffixes)),
            UserWarning,
            stacklevel=2,
        )


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

    # Browser refresh (debug): SSE endpoint + injected script; polls mtimes for reload_include
    # None = auto (follows debug); True/False = explicit override
    dev_browser_reload: bool | None = None

    # Security
    secret_key: str = ""
    allowed_hosts: tuple[str, ...] = ("*",)
    csp_nonce_enabled: bool = False
    strict_transport_security: str | None = None

    # Templates
    template_dir: str | Path = "templates"
    component_dirs: tuple[
        str | Path, ...
    ] = ()  # Additional template directories (e.g. components, partials)
    extra_loaders: tuple[Any, ...] = ()  # Kida Loader instances, tried first (CMS, DB, state)
    autoescape: bool = True
    trim_blocks: bool = True
    lstrip_blocks: bool = True
    strict_undefined: bool = True
    static_context: MappingProxyType[str, Any] | dict[str, Any] | None = (
        None  # Compile-time constants for kida partial evaluator; frozen to MappingProxyType
    )

    # Static files
    static_dir: str | Path | None = "static"
    static_url: str = "/static"

    # SSE
    sse_heartbeat_interval: float = 15.0
    sse_retry_ms: int | None = None
    sse_close_event: str | None = None

    # Suspense error fallback — used when deferred values fail after shell is sent.
    # Per-route ``Suspense(error_block=...)`` takes precedence over these globals.
    suspense_error_template: str | None = None  # Template containing the fallback block
    suspense_error_block: str = "fallback"  # Block name within the error template

    # MCP (Model Context Protocol)
    mcp_path: str = "/mcp"

    # htmx safe target — auto-add hx-target="this" to event-driven elements
    safe_target: bool = True

    # SSE lifecycle — data-sse-state attribute + chirp:sse:connected/disconnected events
    sse_lifecycle: bool = True

    # View Transitions — tiered opt-in for the View Transitions API.
    #   False / "off"  — inject nothing (default)
    #   True  / "htmx" — htmx globalViewTransitions only (baseline, all browsers)
    #   "full"         — htmx JS + MPA CSS/meta (cross-document, no Firefox yet)
    view_transitions: bool | str = False

    # Speculation Rules API — prefetch/prerender predictions for instant MPA navigation.
    #   False / "off"          — inject nothing (default)
    #   True  / "conservative" — prefetch linked pages on hover (safe for all apps)
    #   "moderate"             — prefetch eagerly, prerender on hover
    #   "eager"                — prerender eagerly (routes must be side-effect-free)
    speculation_rules: bool | str = False

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

    # Upload limits (multipart / file-upload bodies). These are distinct from
    # max_content_length, which is not enforced by the request pipeline. The
    # upload limits below are enforced where the bytes actually flow:
    #   - max_upload_size: hard ceiling on the request body for upload/form
    #     reads; Request.body()/stream() abort with 413 PayloadTooLarge before
    #     the chunks are joined into RAM (reject-before-OOM).
    #   - upload_spool_threshold: bytes an UploadFile keeps in memory before it
    #     spills to a temp file on disk (stdlib SpooledTemporaryFile).
    #   - max_upload_parts: cap on the number of multipart parts, rejecting a
    #     multipart bomb with 413 PayloadTooLarge.
    max_upload_size: int = 16 * 1024 * 1024  # 16 MB upload/multipart body ceiling
    upload_spool_threshold: int = 1024 * 1024  # 1 MB held in RAM before spilling to disk
    max_upload_parts: int = 1000  # multipart part-count cap

    # Production (pounce Phase 6 features)
    workers: int = 0  # 0 = auto-detect from CPU count (multi-worker for production)
    # Pounce worker execution: "auto" | "sync" | "async" | "subinterpreter"
    # sync = blocking I/O, no asyncio; async = event loop; auto = sync on 3.14t, async on GIL
    # subinterpreter = PEP 734 concurrent.interpreters (thread-like perf, process-like isolation)
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

    # Cache
    cache_backend: str = "memory"
    cache_default_ttl: int = 300
    cache_middleware_enabled: bool = False

    # Internationalization (i18n)
    i18n_enabled: bool = False
    i18n_default_locale: str = "en"
    i18n_supported_locales: tuple[str, ...] = ("en",)
    i18n_directory: str | Path = "locales"
    i18n_cookie_name: str = "chirp_locale"
    i18n_url_prefix: bool = False

    # Enterprise scale (12-factor, observability, shared state)
    env: str = "development"  # development | staging | production
    redis_url: str | None = None
    audit_sink: str | None = "log"  # "log" | "none" | custom
    feature_flags: tuple[tuple[str, bool], ...] = ()  # (name, value) pairs
    http_timeout: float = 30.0
    http_retries: int = 0
    skip_contract_checks: bool = False
    lazy_pages: bool = False

    # Debug fragment validator (debug mode only) — warns when fragment
    # responses leak <!DOCTYPE or duplicate shell-region ids. Opt out by
    # setting False for apps that render pre-serialized HTML fragments
    # containing intentional id repetition.
    debug_fragment_validator: bool = True

    def __post_init__(self) -> None:
        # Resolve dev_browser_reload sentinel: None → follow debug flag.
        if self.dev_browser_reload is None:
            object.__setattr__(self, "dev_browser_reload", self.debug)

        # Freeze mutable static_context dict → MappingProxyType so the
        # "frozen dataclass" guarantee extends to nested containers.
        sc = self.static_context
        if isinstance(sc, dict):
            object.__setattr__(self, "static_context", MappingProxyType(sc))

        # Guard: empty secret_key outside development is a security risk.
        if self.env != "development" and not self.secret_key:
            from chirp.errors import ConfigurationError

            raise ConfigurationError(
                f"secret_key must not be empty when env={self.env!r}. "
                "Set CHIRP_SECRET_KEY or pass secret_key= to AppConfig."
            )

        # Validate view_transitions / speculation_rules via their normalizers
        # (single source of truth for accepted values).
        from chirp.server.view_transitions import normalize_view_transitions

        normalize_view_transitions(self.view_transitions)

        from chirp.server.speculation_rules import normalize_speculation_rules

        normalize_speculation_rules(self.speculation_rules)

    @classmethod
    def from_env(cls, prefix: str = "CHIRP_") -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with the given prefix (default ``CHIRP_``).
        Unset vars use AppConfig defaults.

        If ``python-dotenv`` is installed (``pip install chirp[config]``),
        loads ``.env`` from the current directory before reading env.

        Env vars (with CHIRP_ prefix):
            SECRET_KEY, DEBUG, ENV, HOST, PORT, ALLOWED_HOSTS,
            LOG_FORMAT (auto|text|json — forwarded to Pounce),
            SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE,
            REDIS_URL, AUDIT_SINK, SKIP_CONTRACT_CHECKS, LAZY_PAGES,
            HTTP_TIMEOUT, HTTP_RETRIES,
            FEATURE_<NAME>=true|false (e.g. CHIRP_FEATURE_X=true)

        Railway compatibility:
            If CHIRP_PORT is unset, from_env() falls back to Railway's PORT.
            If CHIRP_HOST is unset in a Railway environment, host defaults to
            "0.0.0.0". If CHIRP_ALLOWED_HOSTS is unset and
            RAILWAY_PUBLIC_DOMAIN is present, allowed_hosts includes that
            domain and healthcheck.railway.app.
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

        _warn_unknown_env_vars(
            p,
            frozenset(
                {
                    "HOST",
                    "PORT",
                    "ALLOWED_HOSTS",
                    "DEBUG",
                    "SECRET_KEY",
                    "ENV",
                    "REDIS_URL",
                    "AUDIT_SINK",
                    "LOG_FORMAT",
                    "HTTP_TIMEOUT",
                    "HTTP_RETRIES",
                    "SKIP_CONTRACT_CHECKS",
                    "LAZY_PAGES",
                    "SENTRY_DSN",
                    "SENTRY_ENVIRONMENT",
                    "SENTRY_RELEASE",
                    "MAX_UPLOAD_SIZE",
                    "UPLOAD_SPOOL_THRESHOLD",
                    "MAX_UPLOAD_PARTS",
                }
            ),
        )

        host = os.environ.get(f"{p}HOST")
        if host is None:
            host = (
                "0.0.0.0"  # noqa: S104 - Railway requires binding the public service port.
                if os.environ.get("RAILWAY_ENVIRONMENT_ID")
                or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
                else "127.0.0.1"
            )

        return cls(
            host=host,
            port=_env_int_first((f"{p}PORT", "PORT"), 8000),
            allowed_hosts=_env_allowed_hosts(p),
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
            max_upload_size=_env_int(f"{p}MAX_UPLOAD_SIZE", 16 * 1024 * 1024),
            upload_spool_threshold=_env_int(f"{p}UPLOAD_SPOOL_THRESHOLD", 1024 * 1024),
            max_upload_parts=_env_int(f"{p}MAX_UPLOAD_PARTS", 1000),
        )

    def feature(self, name: str) -> bool:
        """Return True if the named feature flag is enabled."""
        for k, v in self.feature_flags:
            if k == name:
                return v
        return False

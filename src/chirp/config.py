"""Application configuration.

AppConfig is a frozen dataclass — immutable after creation, IDE-autocompletable,
no string-key dict lookups.
"""

import os
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pounce.display import DisplayConfig

# Shared default for the request-body / multipart-upload byte ceilings (16 MB).
# Named so __post_init__ can tell "user left max_upload_size at its default"
# (safe to clamp down to a smaller body cap) from "user explicitly raised it
# above the body cap" (a real misconfiguration worth a hard error).
_DEFAULT_BODY_SIZE = 16 * 1024 * 1024


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


def _env_trusted_proxies(prefix: str) -> tuple[str, ...]:
    """Read TRUSTED_PROXIES as a comma/space-separated tuple (empty default).

    Unlike _env_allowed_hosts, an unset value stays () so pounce ignores
    X-Forwarded-For entirely — there is no implicit '*' fallback.
    """
    raw = os.environ.get(f"{prefix}TRUSTED_PROXIES")
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.replace(",", " ").split() if part.strip())


def _env_log_format(key: str, default: str) -> str:
    """Read log format from env; invalid values fall back to default."""
    val = (os.environ.get(key) or "").lower().strip()
    if val in ("auto", "text", "json"):
        return val
    return default


def _env_log_level(key: str, default: str) -> str:
    """Read log level from env; invalid values fall back to default."""
    val = (os.environ.get(key) or "").lower().strip()
    if val in ("debug", "info", "warning", "error", "critical"):
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
    secret_key: str = field(default="", repr=False)
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
    # Files at/above this size (bytes) stream from disk in chunks instead of
    # being read into memory in one shot; caps worker RSS for large static GETs.
    static_stream_threshold: int = 1024 * 1024  # 1 MiB

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

    # htmx — hypermedia transport. Opt-in injection mirroring ``alpine`` above:
    # when ``htmx=True`` Chirp compiles one exact managed bundle and injects it
    # before ``</body>`` (with a per-request CSP nonce). The verified 2.0.10
    # baseline is core-only; exact pin 4.0.0-beta5 selects the provisional
    # core -> htmx-2-compat -> hx-sse bundle. ``data-chirp="htmx"`` dedups the
    # complete bundle when a template explicitly owns it.
    # Default off — never global default-on; templates that hardcode htmx
    # (chirp-ui shell/boost, the v2 scaffold) keep working unchanged.
    htmx: bool = False
    htmx_version: str = "2.0.10"  # Exact pin; 4.0.0-beta5 is the preview allowlist

    # Islands runtime — framework-agnostic high-state mount lifecycle
    islands: bool = False
    islands_version: str = "1"
    islands_contract_strict: bool = False  # Validate mount metadata in app.check()

    # Passkeys / WebAuthn — vendored inline JS bridge (window.chirp.passkeys).
    # Opt-in injection mirroring ``islands``/``htmx`` above: when ``passkeys=True``
    # Chirp injects a dependency-free base64url + navigator.credentials bridge
    # before ``</body>`` (with a per-request CSP nonce), deduped on
    # ``data-chirp="passkeys"``. The server verbs need ``chirp[passkeys]``; the
    # bridge itself loads nothing external. See chirp.security.passkeys.
    passkeys: bool = False
    passkeys_version: str = "1"

    # Request body / upload limits. Two distinct concerns, two distinct knobs:
    #
    #   - max_request_body_size: the GENERAL envelope — a hard ceiling on the
    #     raw request body for EVERY content type (JSON, text, urlencoded, and
    #     multipart). Request.body()/stream() abort with 413 PayloadTooLarge as
    #     bytes arrive, before the chunks are joined into RAM (reject-before-OOM).
    #   - max_upload_size: the MULTIPART-SPECIFIC cap — the total accumulated
    #     size of multipart/form-data parts. Enforced by the multipart parser as
    #     parts stream in. Distinct from max_request_body_size so an app can cap
    #     file-upload payloads independently of plain JSON/text bodies. It is the
    #     inner cap and should be <= max_request_body_size (the outer envelope).
    #   - upload_spool_threshold: bytes an UploadFile keeps in memory before it
    #     spills to a temp file on disk (stdlib SpooledTemporaryFile).
    #   - max_upload_parts: cap on the number of multipart parts, rejecting a
    #     multipart bomb with 413 PayloadTooLarge.
    max_request_body_size: int = 16 * 1024 * 1024  # 16 MB general request-body ceiling
    max_upload_size: int = 16 * 1024 * 1024  # 16 MB multipart total ceiling
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

    # Health probes (auto-mounted): /health (liveness, plain 200) and /ready
    # (readiness — runs registered checks + gates on the startup-complete flag,
    # 503 until ready). Auto-mounted unless a user route claims the path; probe
    # paths short-circuit before the secure middleware stack + commit teardown.
    health_path: str = "/health"
    ready_path: str = "/ready"

    # Phase 6.2: Rate Limiting
    rate_limit_enabled: bool = False
    rate_limit_requests_per_second: float = 100.0
    rate_limit_burst: int = 200
    # Max distinct client IPs tracked by the per-IP rate limiter before LRU
    # eviction; caps limiter memory under a wide/spoofed source-IP fan-out.
    rate_limit_max_tracked_ips: int = 100_000

    # Proxy / forwarded headers
    # Trusted reverse-proxy peer IPs/hostnames whose X-Forwarded-For is honored;
    # maps to pounce ServerConfig.trusted_hosts. X-Forwarded-For is ignored
    # entirely when this is empty (the default), so the request client IP is the
    # raw socket peer. "*" trusts every direct peer — use only on a locked-down
    # network (the trusted_proxies contract warns on "*" outside development).
    trusted_proxies: tuple[str, ...] = ()
    # Number of trailing X-Forwarded-For hops to trust when deriving the client
    # IP behind a reverse proxy (1 = trust the single proxy in front of the
    # app). Only takes effect when the direct peer is one of `trusted_proxies`
    # (mapped to pounce's trusted_hosts); when `trusted_proxies` is empty,
    # X-Forwarded-* headers are ignored entirely and this hop count is moot. The
    # real client IP is read N positions from the RIGHT of the chain. Must be
    # >= 1 — to ignore X-Forwarded-For entirely leave `trusted_proxies` empty
    # (NOT this set to 0; pounce rejects < 1 and AppConfig fails fast below).
    forwarded_for_trusted_hops: int = 1

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
    # Pounce startup display identity (name/tagline/version/lines/signage).
    # Forwarded unchanged as ServerConfig.display; Pounce owns precedence
    # (CLI → env → this value → pyproject → app hook), signage modes, and
    # JSON startup fields. None preserves Pounce's unset behavior. Import
    # ``DisplayConfig`` from ``pounce.display`` — Chirp does not redefine it.
    display: DisplayConfig | None = None

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
    redis_url: str | None = field(default=None, repr=False)
    audit_sink: str | None = "log"  # "log" | "none" | custom
    feature_flags: tuple[tuple[str, bool], ...] = ()  # (name, value) pairs
    http_timeout: float = 30.0
    http_retries: int = 0
    skip_contract_checks: bool = False
    skip_migrations: bool = False
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

        # Invariant: the multipart cap is the inner envelope and must not exceed
        # the general body cap (otherwise the body cap would reject first,
        # making the upload cap unreachable). If the upload cap is still at its
        # default, silently clamp it to the (smaller) body cap — the common case
        # of "I only lowered the overall body limit" should just work. If the
        # caller *explicitly* raised the upload cap above the body cap, that is a
        # real misconfiguration: fail loud at construction.
        if self.max_upload_size > self.max_request_body_size:
            if self.max_upload_size == _DEFAULT_BODY_SIZE:
                object.__setattr__(self, "max_upload_size", self.max_request_body_size)
            else:
                from chirp.errors import ConfigurationError

                raise ConfigurationError(
                    f"max_upload_size ({self.max_upload_size}) must not exceed "
                    f"max_request_body_size ({self.max_request_body_size}); the "
                    "multipart cap is the inner envelope of the general body cap."
                )

        # Guard: empty secret_key outside development is a security risk.
        if self.env != "development" and not self.secret_key:
            from chirp.errors import ConfigurationError

            raise ConfigurationError(
                f"secret_key must not be empty when env={self.env!r}. "
                "Set CHIRP_SECRET_KEY or pass secret_key= to AppConfig."
            )

        # Guard: forwarded_for_trusted_hops < 1 is rejected by pounce at launch.
        # Fail fast at construction instead so the misconfig surfaces here, not
        # deep in the production launch path. To IGNORE X-Forwarded-For, leave
        # trusted_proxies empty — do NOT set this to 0.
        if self.forwarded_for_trusted_hops < 1:
            from chirp.errors import ConfigurationError

            raise ConfigurationError(
                f"forwarded_for_trusted_hops ({self.forwarded_for_trusted_hops}) must be >= 1; "
                "pounce rejects < 1. Set trusted_proxies to a non-empty tuple to actually "
                "honor X-Forwarded-For (the hop count only takes effect when the direct peer "
                "is a trusted proxy)."
            )

        # Validate view_transitions / speculation_rules via their normalizers
        # (single source of truth for accepted values).
        from chirp.server.view_transitions import normalize_view_transitions

        normalize_view_transitions(self.view_transitions)

        from chirp.server.speculation_rules import normalize_speculation_rules

        normalize_speculation_rules(self.speculation_rules)

    @classmethod
    def from_env(cls, prefix: str = "CHIRP_", **overrides: Any) -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with the given prefix (default ``CHIRP_``).
        Unset vars use AppConfig defaults. Pass ``**overrides`` to set or
        replace fields after env loading (e.g.
        ``AppConfig.from_env(template_dir="pages", worker_mode="async")``).

        If ``python-dotenv`` is installed (``pip install chirp[config]``),
        loads ``.env`` from the current directory before reading env.

        Env vars (with CHIRP_ prefix):
            SECRET_KEY, DEBUG, ENV, HOST, PORT, ALLOWED_HOSTS,
            LOG_FORMAT (auto|text|json — forwarded to Pounce),
            SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE,
            REDIS_URL, AUDIT_SINK, SKIP_CONTRACT_CHECKS, SKIP_MIGRATIONS, LAZY_PAGES,
            HTTP_TIMEOUT, HTTP_RETRIES,
            TRUSTED_PROXIES (comma/space-separated reverse-proxy peers),
            FORWARDED_FOR_TRUSTED_HOPS (int >= 1),
            HEALTH_PATH, READY_PATH (auto-mounted probe paths),
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
                    "LOG_LEVEL",
                    "HTTP_TIMEOUT",
                    "HTTP_RETRIES",
                    "SKIP_CONTRACT_CHECKS",
                    "SKIP_MIGRATIONS",
                    "LAZY_PAGES",
                    "SENTRY_DSN",
                    "SENTRY_ENVIRONMENT",
                    "SENTRY_RELEASE",
                    "MAX_REQUEST_BODY_SIZE",
                    "MAX_UPLOAD_SIZE",
                    "UPLOAD_SPOOL_THRESHOLD",
                    "MAX_UPLOAD_PARTS",
                    "TRUSTED_PROXIES",
                    "FORWARDED_FOR_TRUSTED_HOPS",
                    "HEALTH_PATH",
                    "READY_PATH",
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

        config = cls(
            host=host,
            port=_env_int_first((f"{p}PORT", "PORT"), 8000),
            allowed_hosts=_env_allowed_hosts(p),
            trusted_proxies=_env_trusted_proxies(p),
            forwarded_for_trusted_hops=_env_int(f"{p}FORWARDED_FOR_TRUSTED_HOPS", 1),
            log_format=_env_log_format(f"{p}LOG_FORMAT", "auto"),
            log_level=_env_log_level(f"{p}LOG_LEVEL", "info"),
            debug=debug,
            secret_key=os.environ.get(f"{p}SECRET_KEY", ""),
            env=env_val,
            redis_url=os.environ.get(f"{p}REDIS_URL") or None,
            audit_sink=os.environ.get(f"{p}AUDIT_SINK", "log") or None,
            feature_flags=tuple(feature_flags),
            http_timeout=_env_float(f"{p}HTTP_TIMEOUT", 30.0),
            http_retries=_env_int(f"{p}HTTP_RETRIES", 0),
            skip_contract_checks=_env_bool(f"{p}SKIP_CONTRACT_CHECKS", False),
            skip_migrations=_env_bool(f"{p}SKIP_MIGRATIONS", False),
            lazy_pages=_env_bool(f"{p}LAZY_PAGES", False),
            sentry_dsn=os.environ.get(f"{p}SENTRY_DSN") or None,
            sentry_environment=os.environ.get(f"{p}SENTRY_ENVIRONMENT") or None,
            sentry_release=os.environ.get(f"{p}SENTRY_RELEASE") or None,
            max_request_body_size=_env_int(f"{p}MAX_REQUEST_BODY_SIZE", 16 * 1024 * 1024),
            max_upload_size=_env_int(f"{p}MAX_UPLOAD_SIZE", 16 * 1024 * 1024),
            upload_spool_threshold=_env_int(f"{p}UPLOAD_SPOOL_THRESHOLD", 1024 * 1024),
            max_upload_parts=_env_int(f"{p}MAX_UPLOAD_PARTS", 1000),
            health_path=os.environ.get(f"{p}HEALTH_PATH", "/health"),
            ready_path=os.environ.get(f"{p}READY_PATH", "/ready"),
        )
        if overrides:
            config = replace(config, **overrides)
        return config

    def feature(self, name: str) -> bool:
        """Return True if the named feature flag is enabled."""
        for k, v in self.feature_flags:
            if k == name:
                return v
        return False

---
title: Configuration
description: AppConfig frozen dataclass and all configuration options
draft: false
weight: 90
lang: en
type: doc
tags: [configuration, appconfig, settings]
keywords: [config, appconfig, settings, debug, host, port, secret-key, template-dir]
category: explanation
---

## AppConfig

Chirp uses a frozen dataclass for configuration. Every field has IDE autocomplete, type checking, and no runtime `KeyError` surprises.

```python
from chirp import App, AppConfig

config = AppConfig(
    debug=True,
    host="0.0.0.0",
    port=8000,
    secret_key="change-me-in-production",
    template_dir="templates/",
)

app = App(config=config)
```

`AppConfig` is `@dataclass(frozen=True, slots=True)`. Once created, it cannot be mutated. This is intentional -- config should not change after the app starts.

## Field Stability

`AppConfig` is a stable top-level API. Most fields are part of the 1.0
compatibility promise. A few fields expose younger subsystems and remain
provisional until those subsystems are stabilized.

## Stable Configuration Fields

### Server

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | `str` | `"127.0.0.1"` | Bind address for `app.run()` and `chirp run` |
| `port` | `int` | `8000` | Bind port for `app.run()` and `chirp run` |
| `debug` | `bool` | `False` | Enable debug mode, rich errors, DevTools, and template auto-reload |
| `env` | `str` | `"development"` | Environment label; non-development requires a non-empty `secret_key` |

### Development Reload

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reload_include` | `tuple[str, ...]` | `(".html", ".css", ".md")` | File suffixes watched by browser reload; use `()` to disable browser reload |
| `reload_dirs` | `tuple[str, ...]` | `()` | Extra directories watched alongside the current working directory |
| `dev_browser_reload` | `bool \| None` | `None` | Browser refresh injection; `None` follows `debug` |
| `reload_timeout` | `float` | `30.0` | Pounce hot-reload drain timeout |

### Security

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `secret_key` | `str` | `""` | Secret key for sessions, CSRF, and signed state |
| `allowed_hosts` | `tuple[str, ...]` | `("*",)` | Host allowlist for production host validation |
| `csp_nonce_enabled` | `bool` | `False` | Enable nonce-aware CSP helpers |
| `strict_transport_security` | `str \| None` | `None` | Strict-Transport-Security header value |
| `max_content_length` | `int` | `16777216` | Maximum request body size in bytes (16 MB) |

### Templates

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `template_dir` | `str \| Path` | `"templates"` | Directory for Kida templates |
| `component_dirs` | `tuple[str \| Path, ...]` | `()` | Additional component/template directories |
| `extra_loaders` | `tuple[Any, ...]` | `()` | Kida loaders tried before filesystem loaders |
| `autoescape` | `bool` | `True` | Enable HTML autoescaping |
| `trim_blocks` | `bool` | `True` | Kida whitespace trimming |
| `lstrip_blocks` | `bool` | `True` | Kida leading-whitespace trimming |
| `strict_undefined` | `bool` | `True` | Raise on missing template variables |
| `static_context` | `Mapping \| dict \| None` | `None` | Compile-time constants, frozen to `MappingProxyType` when passed as a dict |

### Static Files

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `static_dir` | `str \| Path \| None` | `"static"` | Directory for static files; `None` disables default static serving |
| `static_url` | `str` | `"/static"` | URL prefix for static files |

### SSE And Suspense

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sse_heartbeat_interval` | `float` | `15.0` | Seconds between SSE heartbeat comments |
| `sse_retry_ms` | `int \| None` | `None` | SSE reconnection interval sent to the client |
| `sse_close_event` | `str \| None` | `None` | Optional close event name emitted before stream shutdown |
| `suspense_error_template` | `str \| None` | `None` | Template containing a global Suspense fallback block |
| `suspense_error_block` | `str` | `"fallback"` | Block name for the global Suspense fallback |

### Browser Runtime Helpers

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `safe_target` | `bool` | `True` | Auto-add `hx-target="this"` to event-driven elements |
| `sse_lifecycle` | `bool` | `True` | Inject SSE connection state and lifecycle events |
| `view_transitions` | `bool \| str` | `False` | View Transitions tier: `False`/`"off"`, `True`/`"htmx"`, or `"full"` |
| `speculation_rules` | `bool \| str` | `False` | Speculation Rules tier: `False`/`"off"`, `True`/`"conservative"`, `"moderate"`, or `"eager"` |
| `delegation` | `bool` | `False` | Inject delegated handlers for swapped copy/compare controls |
| `alpine` | `bool` | `False` | Enable Alpine.js script injection |
| `alpine_version` | `str` | `"3.15.8"` | Pinned Alpine.js CDN version |
| `alpine_csp` | `bool` | `False` | Use the CSP-safe Alpine build |
| `htmx` | `bool` | `False` | Inject the htmx core script (satisfies the `htmx_provisioning` contract) |
| `htmx_version` | `str` | `"2.0.4"` | Pinned htmx CDN version |
| `htmx_sse` | `bool` | `False` | Also inject the htmx SSE extension |

### Production Server

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `workers` | `int` | `0` | Pounce worker count; `0` lets pounce auto-detect |
| `worker_mode` | `str` | `"auto"` | Pounce worker execution mode; use `"async"` when registering worker lifecycle hooks |
| `metrics_enabled` | `bool` | `False` | Enable Prometheus metrics |
| `metrics_path` | `str` | `"/metrics"` | Metrics endpoint path |
| `rate_limit_enabled` | `bool` | `False` | Enable rate limiting |
| `rate_limit_requests_per_second` | `float` | `100.0` | Rate limit steady-state rate |
| `rate_limit_burst` | `int` | `200` | Rate limit burst size |
| `request_queue_enabled` | `bool` | `False` | Enable request queueing/load shedding |
| `request_queue_max_depth` | `int` | `1000` | Maximum queued requests |
| `sentry_dsn` | `str \| None` | `None` | Sentry DSN |
| `sentry_environment` | `str \| None` | `None` | Sentry environment name |
| `sentry_release` | `str \| None` | `None` | Sentry release identifier |
| `sentry_traces_sample_rate` | `float` | `0.1` | Sentry tracing sample rate |
| `otel_endpoint` | `str \| None` | `None` | OpenTelemetry OTLP endpoint |
| `otel_service_name` | `str` | `"chirp-app"` | OpenTelemetry service name |
| `lifecycle_logging` | `bool` | `True` | Enable pounce lifecycle logging |
| `log_format` | `str` | `"auto"` | Logging format: `"auto"`, `"text"`, or `"json"` |
| `log_level` | `str` | `"info"` | Logging level |
| `max_connections` | `int` | `1000` | Maximum concurrent connections |
| `backlog` | `int` | `2048` | Socket listen backlog |
| `keep_alive_timeout` | `float` | `5.0` | HTTP keep-alive timeout |
| `request_timeout` | `float` | `30.0` | Request timeout |
| `ssl_certfile` | `str \| None` | `None` | TLS certificate path |
| `ssl_keyfile` | `str \| None` | `None` | TLS key path |

### Cache And Environment

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cache_backend` | `str` | `"memory"` | Cache backend name |
| `cache_default_ttl` | `int` | `300` | Default cache TTL in seconds |
| `cache_middleware_enabled` | `bool` | `False` | Enable whole-response cache middleware |
| `redis_url` | `str \| None` | `None` | Redis URL for Redis-backed features |
| `audit_sink` | `str \| None` | `"log"` | Lifecycle audit sink: `"log"`, `"none"`, or custom |
| `feature_flags` | `tuple[tuple[str, bool], ...]` | `()` | Feature flags loaded by `from_env()` |
| `http_timeout` | `float` | `30.0` | Default outbound HTTP timeout for Chirp helpers |
| `http_retries` | `int` | `0` | Default outbound HTTP retry count |
| `skip_contract_checks` | `bool` | `False` | Disable debug-mode startup contract checks |
| `lazy_pages` | `bool` | `False` | Lazily load filesystem page modules |
| `debug_fragment_validator` | `bool` | `True` | Enable debug-only fragment response validation |

## Provisional Configuration Fields

These fields are public but tied to subsystems that are still settling before
1.0. Use them when needed, but expect minor-release refinements with changelog
coverage.

| Field | Type | Default | Reason |
|-------|------|---------|--------|
| `mcp_path` | `str` | `"/mcp"` | MCP/tool integration is younger than the core hypermedia surface |
| `islands` | `bool` | `False` | Islands runtime API is still settling |
| `islands_version` | `str` | `"1"` | Version tag for the provisional islands runtime |
| `islands_contract_strict` | `bool` | `False` | Contract strictness will stabilize with the islands API |
| `websocket_compression` | `bool` | `True` | Pounce-facing pass-through; Chirp's first-class realtime story is SSE |
| `websocket_max_message_size` | `int` | `10485760` | Pounce-facing pass-through; no Chirp WebSocket return type exists |
| `i18n_enabled` | `bool` | `False` | i18n needs published examples and contract coverage before stabilization |
| `i18n_default_locale` | `str` | `"en"` | Provisional i18n option |
| `i18n_supported_locales` | `tuple[str, ...]` | `("en",)` | Provisional i18n option |
| `i18n_directory` | `str \| Path` | `"locales"` | Provisional i18n option |
| `i18n_cookie_name` | `str` | `"chirp_locale"` | Provisional i18n option |
| `i18n_url_prefix` | `bool` | `False` | Provisional i18n option |

## Debug Mode

When `debug=True`:

- Detailed error pages with tracebacks are shown in the browser
- Templates auto-reload when modified (no server restart needed)
- Stricter validation warnings are surfaced

```python
config = AppConfig(debug=True)
```

:::{warning}
Never enable debug mode in production. It exposes internal details including source code and tracebacks.
:::

## Secret Key

Required for session middleware and CSRF protection. Use a strong random value in production:

```python
import secrets

config = AppConfig(
    secret_key=secrets.token_hex(32),
)
```

:::{note}
If you use `SessionMiddleware` or `CSRFMiddleware` without setting a `secret_key`, Chirp raises a `ConfigurationError` at startup.
:::

## Default Configuration

If you don't pass a config, sensible defaults are used:

```python
app = App()  # Uses default AppConfig
```

This is equivalent to:

```python
app = App(config=AppConfig())
```

## Next Steps

- [[docs/about/core-concepts/app-lifecycle|App Lifecycle]] -- How the app freezes
- [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]] -- Middleware that uses config
- [[docs/reference/api|API Reference]] -- Complete API surface

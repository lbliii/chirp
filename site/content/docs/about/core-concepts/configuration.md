---
title: Configuration
description: How AppConfig works — set fields in code for dev, load from the environment for prod, both produce the same frozen config.
draft: false
weight: 90
lang: en
type: doc
tags: [configuration, appconfig, settings]
keywords: [config, appconfig, settings, debug, host, port, secret-key, from_env, env-vars]
category: explanation
---

## Overview

Chirp reads all configuration from one immutable object: `AppConfig`. You set
fields in code for local development, or load them from environment variables
for production — both produce the same frozen config that the app runs against.

For most apps, start here:

::::{code-tabs}

```python title="Local development"
# Set fields in code
from chirp import App, AppConfig

app = App(config=AppConfig(debug=True, secret_key="dev-only"))
```

```python title="Production"
# Load from the environment
from chirp import App, AppConfig

app = App(config=AppConfig.from_env())  # reads CHIRP_SECRET_KEY, CHIRP_ENV, CHIRP_PORT, ...
```

::::

Pass no config and you get the defaults:

```python
app = App()  # same as App(config=AppConfig())
```

Every field has IDE autocomplete and type checking, so there are no runtime
`KeyError` surprises. The fields you reach for most often are below; the full
catalog and exact signatures live in the
[[docs/reference/api|complete field and signature reference]].

:::{note}
`AppConfig` is `@dataclass(frozen=True, slots=True)` — it cannot be mutated after
it is created. The app freezes this config when it starts; see
[[docs/about/core-concepts/app-lifecycle|how the app freezes configuration at startup]].
:::

## Load configuration from the environment

`AppConfig.from_env()` builds a config from environment variables — the 12-factor
path you want in production. Unset variables fall back to the `AppConfig`
defaults, and any keyword you pass overrides the result:

```python
app = App(config=AppConfig.from_env(template_dir="pages", worker_mode="async"))
```

Variables use the `CHIRP_` prefix (override with `from_env(prefix="MYAPP_")`).
The commonly-set ones:

:::{list-table}
:header-rows: 1

* - Variable
  - Sets
* - `CHIRP_SECRET_KEY`
  - `secret_key`
* - `CHIRP_ENV`
  - `env` (`development` / `staging` / `production`)
* - `CHIRP_DEBUG`
  - `debug`
* - `CHIRP_HOST`, `CHIRP_PORT`
  - `host`, `port`
* - `CHIRP_ALLOWED_HOSTS`
  - `allowed_hosts` (comma/space-separated)
* - `CHIRP_TRUSTED_PROXIES`
  - `trusted_proxies` (comma/space-separated)
* - `CHIRP_FEATURE_<NAME>`
  - a `feature_flags` entry (`CHIRP_FEATURE_BETA=true`)
:::

If `python-dotenv` is installed (`pip install chirp[config]`), `from_env()` loads
a `.env` file from the current directory first. On Railway, it falls back to
the platform's `PORT`, binds `0.0.0.0`, and — when `CHIRP_ALLOWED_HOSTS` is
unset — sets `allowed_hosts` to your `RAILWAY_PUBLIC_DOMAIN` plus
`healthcheck.railway.app`.

:::{note} See also

For the full env-var list, reverse-proxy headers, and a copy-pasteable prod
config, see [[docs/quality/deployment/production|Running behind a reverse proxy]].
:::

## Fields you set by hand

These are the knobs most apps touch directly. Everything else has a default that
works out of the box.

:::{list-table}
:header-rows: 1

* - Field
  - Type
  - Default
  - What it does
* - `debug`
  - `bool`
  - `False`
  - Rich error pages, DevTools, template auto-reload
* - `secret_key`
  - `str`
  - `""`
  - Signing key for sessions, CSRF, and signed state
* - `host`
  - `str`
  - `"127.0.0.1"`
  - Bind address for `app.run()` / `chirp run`
* - `port`
  - `int`
  - `8000`
  - Bind port for `app.run()` / `chirp run`
* - `env`
  - `str`
  - `"development"`
  - Environment label; a non-development value requires a `secret_key`
* - `template_dir`
  - `str | Path`
  - `"templates"`
  - Directory for Kida templates
* - `static_dir`
  - `str | Path | None`
  - `"static"`
  - Static-file directory; `None` disables default static serving
* - `allowed_hosts`
  - `tuple[str, ...]`
  - `("*",)`
  - Host allowlist for production host validation
* - `worker_mode`
  - `str`
  - `"auto"`
  - Pounce worker execution: `"auto"`, `"sync"`, `"async"`, or `"subinterpreter"`
:::

The remaining fields group by concern below — open the one you need.

## Debug mode

When `debug=True`:

- Detailed error pages with tracebacks are shown in the browser.
- Templates auto-reload when modified (no server restart).
- Stricter validation warnings are surfaced.

```python
app = App(config=AppConfig(debug=True, secret_key="dev-only"))
```

:::{danger}
Never enable `debug` in production. It exposes internal details — source code
and full tracebacks — in the browser.
:::

## Secret key

`secret_key` signs sessions, CSRF tokens, and signed state. Use a strong random
value in production, and read it from the environment rather than hard-coding it:

```python
import os

app = App(config=AppConfig(secret_key=os.environ["CHIRP_SECRET_KEY"]))
```

:::{note}
Constructing `AppConfig` with `env` set to anything other than `"development"`
and an empty `secret_key` raises `ConfigurationError`. Adding `SessionMiddleware`
or `CSRFMiddleware` without a `secret_key` also raises `ConfigurationError`. To
wire the secure-by-default stack, see
[[docs/quality/deployment/auth-hardening|wire the secure-by-default stack]].
:::

## Reference field groups

::::{dropdown} Server, reload & templates
:icon: server

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reload_include` | `tuple[str, ...]` | `(".html", ".css", ".md")` | File suffixes watched by browser reload; use `()` to disable |
| `reload_dirs` | `tuple[str, ...]` | `()` | Extra directories watched alongside the working directory |
| `dev_browser_reload` | `bool \| None` | `None` | Browser refresh injection; `None` follows `debug` |
| `reload_timeout` | `float` | `30.0` | Pounce hot-reload drain timeout |
| `component_dirs` | `tuple[str \| Path, ...]` | `()` | Additional component/template directories |
| `extra_loaders` | `tuple[Any, ...]` | `()` | Kida loaders tried before filesystem loaders |
| `autoescape` | `bool` | `True` | Enable HTML autoescaping |
| `trim_blocks` | `bool` | `True` | Kida whitespace trimming |
| `lstrip_blocks` | `bool` | `True` | Kida leading-whitespace trimming |
| `strict_undefined` | `bool` | `True` | Raise on missing template variables |
| `static_context` | `Mapping \| dict \| None` | `None` | Compile-time constants, frozen to `MappingProxyType` when passed as a dict |
| `static_url` | `str` | `"/static"` | URL prefix for static files |
| `static_stream_threshold` | `int` | `1048576` | File size (bytes) at/above which static files stream from disk instead of buffering (1 MiB) |
::::{/dropdown}

::::{dropdown} Security & request limits
:icon: shield

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `csp_nonce_enabled` | `bool` | `False` | Enable nonce-aware CSP helpers |
| `strict_transport_security` | `str \| None` | `None` | Strict-Transport-Security header value |
| `max_request_body_size` | `int` | `16777216` | General request-body ceiling for **every** content type (16 MiB); oversize bodies are rejected with 413 *before* buffering into RAM |
| `max_upload_size` | `int` | `16777216` | Multipart-specific ceiling on total `multipart/form-data` part size (16 MiB); must be `<=` `max_request_body_size` |
| `upload_spool_threshold` | `int` | `1048576` | Bytes an `UploadFile` keeps in RAM before spilling to a temp file (1 MiB) |
| `max_upload_parts` | `int` | `1000` | Maximum number of multipart parts; rejects multipart bombs |
::::{/dropdown}

::::{dropdown} Production server & observability
:icon: network
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `workers` | `int` | `0` | Pounce worker count; `0` lets pounce auto-detect |
| `metrics_enabled` | `bool` | `False` | Enable Prometheus metrics |
| `metrics_path` | `str` | `"/metrics"` | Metrics endpoint path |
| `health_path` | `str` | `"/health"` | Auto-mounted liveness probe path (plain 200; K8s `livenessProbe`). `CHIRP_HEALTH_PATH` |
| `ready_path` | `str` | `"/ready"` | Auto-mounted readiness probe path (runs registered checks + startup gate; 503 until ready; K8s `readinessProbe`). `CHIRP_READY_PATH` |
| `rate_limit_enabled` | `bool` | `False` | Enable rate limiting |
| `rate_limit_requests_per_second` | `float` | `100.0` | Rate limit steady-state rate |
| `rate_limit_burst` | `int` | `200` | Rate limit burst size |
| `rate_limit_max_tracked_ips` | `int` | `100000` | Max distinct client IPs the per-IP rate limiter tracks before LRU eviction |
| `trusted_proxies` | `tuple[str, ...]` | `()` | Reverse-proxy peer IPs/hostnames whose `X-Forwarded-For` is honored. Empty ignores `X-Forwarded-For`; `"*"` trusts every peer (spoofing risk). See [[docs/quality/deployment/production|Running behind a reverse proxy]]. |
| `forwarded_for_trusted_hops` | `int` | `1` | Trailing `X-Forwarded-For` hops to trust. Must be `>= 1` (construction fails fast otherwise); only honored when `trusted_proxies` is non-empty |
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
::::{/dropdown}

::::{dropdown} SSE, Suspense & browser runtime
:icon: zap

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sse_heartbeat_interval` | `float` | `15.0` | Seconds between SSE heartbeat comments |
| `sse_retry_ms` | `int \| None` | `None` | SSE reconnection interval sent to the client |
| `sse_close_event` | `str \| None` | `None` | Optional close event name emitted before stream shutdown |
| `suspense_error_template` | `str \| None` | `None` | Template containing a global Suspense fallback block |
| `suspense_error_block` | `str` | `"fallback"` | Block name for the global Suspense fallback |
| `safe_target` | `bool` | `True` | Auto-add `hx-target="this"` to event-driven elements |
| `sse_lifecycle` | `bool` | `True` | Inject SSE connection state and lifecycle events |
| `view_transitions` | `bool \| str` | `False` | View Transitions tier: `False`/`"off"`, `True`/`"htmx"`, or `"full"` |
| `speculation_rules` | `bool \| str` | `False` | Speculation Rules tier: `False`/`"off"`, `True`/`"conservative"`, `"moderate"`, or `"eager"` |
| `delegation` | `bool` | `False` | Inject delegated handlers for swapped copy/compare controls |
| `alpine` | `bool` | `False` | Enable Alpine.js script injection |
| `alpine_version` | `str` | `"3.15.8"` | Pinned Alpine.js CDN version |
| `alpine_csp` | `bool` | `False` | Use the CSP-safe Alpine build |
| `htmx` | `bool` | `False` | Enable opt-in managed htmx bundle injection |
| `htmx_version` | `str` | `"2.0.10"` | Exact htmx pin; `"4.0.0-beta5"` selects the provisional preview bundle |
::::{/dropdown}

The preview opt-in is intentionally exact and reversible:

```python
config = AppConfig(htmx=True, htmx_version="4.0.0-beta5")
```

It injects htmx core, `htmx-2-compat`, and `hx-sse` in that order with the
same live CSP nonce. Unknown htmx 4 pins fail during app freeze. Roll back with
`htmx_version="2.0.10"`; the default and generated scaffolds remain on that
verified htmx 2 baseline. See [[docs/build-apps/ui-extensions/htmx4-preview|the
htmx 4 preview and rollback guide]].

::::{dropdown} Cache & environment
:icon: database

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
| `skip_migrations` | `bool` | `False` | Skip the on-boot migration run (`CHIRP_SKIP_MIGRATIONS`); pair with a `chirp migrate` deploy job |
| `lazy_pages` | `bool` | `False` | Lazily load filesystem page modules |
| `debug_fragment_validator` | `bool` | `True` | Enable debug-only fragment response validation |
::::{/dropdown}

## Provisional fields

:::{since} 0.8
These fields are public but tied to subsystems still settling before 1.0. Use
them when you need them, but expect minor-release refinements with changelog
coverage.
:::

::::{dropdown} Provisional subsystem fields
:icon: flask
| Field | Type | Default | Reason |
|-------|------|---------|--------|
| `mcp_path` | `str` | `"/mcp"` | MCP/tool integration is younger than the core hypermedia surface |
| `islands` | `bool` | `False` | Islands runtime API is still settling |
| `islands_version` | `str` | `"1"` | Version tag for the provisional islands runtime |
| `islands_contract_strict` | `bool` | `False` | Contract strictness will stabilize with the islands API |
| `passkeys` | `bool` | `False` | Inject the `window.chirp.passkeys` WebAuthn JS bridge (needs `chirp[passkeys]` for the server verbs) |
| `passkeys_version` | `str` | `"1"` | Version tag / cache-bust marker for the provisional passkeys bridge |
| `websocket_compression` | `bool` | `True` | Pounce-facing pass-through; Chirp's first-class realtime story is SSE |
| `websocket_max_message_size` | `int` | `10485760` | Pounce-facing pass-through; no Chirp WebSocket return type exists |
| `i18n_enabled` | `bool` | `False` | i18n needs published examples and contract coverage before stabilization |
| `i18n_default_locale` | `str` | `"en"` | Provisional i18n option |
| `i18n_supported_locales` | `tuple[str, ...]` | `("en",)` | Provisional i18n option |
| `i18n_directory` | `str \| Path` | `"locales"` | Provisional i18n option |
| `i18n_cookie_name` | `str` | `"chirp_locale"` | Provisional i18n option |
| `i18n_url_prefix` | `bool` | `False` | Provisional i18n option |
::::{/dropdown}

## Construction-time validation

`AppConfig.__post_init__` enforces a few invariants when you construct the config,
so misconfigurations fail loud immediately instead of deep in the launch path:

- **Secret key** — empty `secret_key` with `env` not `"development"` raises `ConfigurationError`.
- **Upload caps** — if `max_upload_size` exceeds `max_request_body_size`, Chirp clamps it to the body cap when the upload cap is still at its default, and otherwise raises `ConfigurationError`.
- **Forwarded hops** — `forwarded_for_trusted_hops` below `1` raises `ConfigurationError`. To ignore `X-Forwarded-For`, leave `trusted_proxies` empty rather than lowering this.

## See also

:::{related}
:limit: 3
:section_title: Next Steps
:::

- [[docs/about/core-concepts/app-lifecycle|App lifecycle]] — how the app freezes config at startup
- [[docs/build-apps/request-pipeline/builtin|Built-in middleware]] — middleware that reads config
- [[docs/quality/deployment/production|Production deployment]] — env config behind a reverse proxy
- [[docs/reference/api|API reference]] — the complete field and signature catalog

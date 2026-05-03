# Plan: AppConfig 1.0 Audit

**Status**: Completed initial audit
**Created**: 2026-05-03
**Completed**: 2026-05-03
**Steward**: Public Surface Steward + Narrative Docs Steward

---

## Result

`AppConfig` remains a stable top-level API. The audit found no field that should
be removed or renamed before 1.0 in this pass.

The important clarification is field-level maturity: `AppConfig` is the stable
configuration container, but not every field has the same compatibility weight.
Core server, template, static, security, return-surface, and production-server
fields should be treated as stable. Young subsystem toggles remain provisional
until their surrounding APIs are stabilized.

## Stable Field Groups

These fields are part of the 1.0 compatibility promise unless a later PR adds a
deprecation path:

| Group | Fields |
|-------|--------|
| Server basics | `host`, `port`, `debug`, `env` |
| Development reload | `reload_include`, `reload_dirs`, `dev_browser_reload`, `reload_timeout` |
| Security | `secret_key`, `allowed_hosts`, `csp_nonce_enabled`, `strict_transport_security`, `max_content_length` |
| Templates | `template_dir`, `component_dirs`, `extra_loaders`, `autoescape`, `trim_blocks`, `lstrip_blocks`, `strict_undefined`, `static_context` |
| Static files | `static_dir`, `static_url` |
| SSE and Suspense | `sse_heartbeat_interval`, `sse_retry_ms`, `sse_close_event`, `suspense_error_template`, `suspense_error_block` |
| Core browser helpers | `safe_target`, `sse_lifecycle`, `view_transitions`, `speculation_rules`, `delegation` |
| Alpine integration | `alpine`, `alpine_version`, `alpine_csp` |
| Production server | `workers`, `worker_mode`, `metrics_enabled`, `metrics_path`, `rate_limit_enabled`, `rate_limit_requests_per_second`, `rate_limit_burst`, `request_queue_enabled`, `request_queue_max_depth`, `sentry_dsn`, `sentry_environment`, `sentry_release`, `sentry_traces_sample_rate`, `otel_endpoint`, `otel_service_name`, `lifecycle_logging`, `log_format`, `log_level`, `max_connections`, `backlog`, `keep_alive_timeout`, `request_timeout`, `ssl_certfile`, `ssl_keyfile` |
| Cache | `cache_backend`, `cache_default_ttl`, `cache_middleware_enabled` |
| Environment loading | `redis_url`, `audit_sink`, `feature_flags`, `http_timeout`, `http_retries`, `skip_contract_checks`, `lazy_pages`, `debug_fragment_validator` |

## Provisional Field Groups

These fields stay available, but should not be treated as fully settled until
their feature area is also stable:

| Group | Fields | Reason |
|-------|--------|--------|
| Islands | `islands`, `islands_version`, `islands_contract_strict` | The islands runtime is useful, but the app-author contract is still settling. |
| MCP endpoint | `mcp_path` | MCP/tool integration is young relative to the core hypermedia model. |
| i18n | `i18n_enabled`, `i18n_default_locale`, `i18n_supported_locales`, `i18n_directory`, `i18n_cookie_name`, `i18n_url_prefix` | Internationalization has a clear shape but needs published examples and contract coverage before 1.0 stabilization. |
| WebSocket pass-through | `websocket_compression`, `websocket_max_message_size` | Chirp's first-class realtime story is SSE; WebSocket knobs are pounce-facing configuration. |

## Follow-Ups

1. Add a contract or integration example before stabilizing i18n fields.
2. Decide whether `mcp_path` belongs in stable core config or a tools-specific
   config surface before stabilizing tool APIs.
3. Keep WebSocket fields documented as pounce-facing pass-through unless Chirp
   grows a first-class WebSocket return type.
4. Avoid adding new `AppConfig` fields before 1.0 unless the field removes an
   existing ambiguity or supports an already-documented public contract.

## Documentation Changes

The published configuration guide now lists every current `AppConfig` field and
separates stable from provisional groups. It also corrects stale defaults for
`secret_key` and `static_dir`.

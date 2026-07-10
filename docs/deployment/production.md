# Production Deployment

Guide to deploying Chirp apps with Pounce.

For Railway-specific environment variables, health checks, pre-deploy
migrations, and replica caveats, see [Railway Deployment](railway.md).

## Overview

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), a
free-threading-native ASGI server. Chirp owns hypermedia contracts and app
configuration; Pounce owns server bind/configuration, worker execution,
timeouts, TLS, metrics, and operational preflight checks.

## Quick Start

### Chirp Entrypoint

Use `AppConfig` when starting through Chirp:

```python
from chirp import App, AppConfig

config = AppConfig(
    debug=False,
    secret_key="your-secret-key-here",
    workers=4,
    metrics_enabled=True,
    rate_limit_enabled=True,
)

app = App(config=config)

@app.route("/")
def index():
    return "Hello!"

app.run()
```

Or use the Chirp CLI:

```bash
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

When you start through `app.run()` or `chirp run`, Chirp reads `AppConfig`.
`pounce.toml` is not read by `app.run()` or `chirp run` today.

### Pounce Entrypoint

Use Pounce-native config when starting directly through Pounce:

```bash
pounce serve --app myapp:app --config pounce.toml
```

This is useful when operations teams want a server-native config file. It does
not change Chirp's `AppConfig`, route contracts, or template checks.

## Preflight Checks

Run both checks in CI or before deployment because they validate different
contracts:

```bash
chirp check myapp:app --deploy
pounce check --app myapp:app --config pounce.toml
```

`chirp check` validates Chirp's hypermedia contracts: routes, templates,
blocks, OOB targets, forms, SSE wiring, and app-level checks.

The `--deploy` flag runs the env-aware safety rules (`secret_key`,
`allowed_hosts`, `debug`/`metrics`/`sentry`, `security_stack`, `csp_nonce`) with
**production posture** and treats warnings as errors. It answers "would this app
pass `app.check()` if `env="production"`?" without changing your config — it
builds a throwaway production-posture *view* and never mutates the running app.
It is tighten-only: a genuinely deploy-ready app still passes. Use it in CI as a
deploy gate; use `--warnings-as-errors` alone when you only want strict warnings
without escalating production-only severities.

`pounce check` validates Pounce's server-facing inputs: import path, config
file, bind address, TLS files, worker settings, and related server options.

If you do not use `pounce.toml`, pass the same server flags you use at runtime:

```bash
pounce check --app myapp:app --host 0.0.0.0 --port 8000 --workers 4
```

## Inspect Pounce Config

Pounce 0.7 includes config inspection commands:

```bash
pounce config schema --output-format toml-template
pounce config schema --output-format json
pounce config show --config pounce.toml --output-format toml
```

Use `toml-template` to generate a starting `pounce.toml`, `json` for tooling,
and `config show` to inspect the resolved Pounce config after file and CLI
overrides are merged.

## Worker Lifecycle Hooks

Use `@app.on_worker_startup` and `@app.on_worker_shutdown` for resources that
must be created inside each production worker, such as async HTTP clients or
event-loop-bound database pools.

Worker lifecycle hooks work with Pounce sync and async workers in production:

```python
config = AppConfig(debug=False, workers=4, worker_mode="async")
```

When either worker hook is registered, Chirp configures Pounce 0.9's
`worker_startup_failure="shutdown"` policy so a failed startup hook stops the
worker/server instead of serving with uninitialized worker state. Chirp does
not expose Pounce timeout or executor controls through `AppConfig`.

`worker_mode="subinterpreter"` remains unsupported by Chirp's production
adapter because it receives a live `App` object rather than a Pounce import
path. Use `sync`, `async`, or `auto` and follow the actionable startup error.

## Demo tier vs production tier

Some examples (notably Lucky Cat) pin `workers=1` and keep wallet, trades,
notifications, and the signal bus in process memory so they run offline in CI.
That is a **demo boundary**, not a framework ceiling.

| Concern | Demo (in-memory example) | Production |
|---------|--------------------------|------------|
| Workers | `1` | `N` with shared signal backplane |
| State | In-process stores | External source of truth |
| Signals | In-process fan-out | Private Redis backplane via `redis_url` |
| Secret | Dev fallback in `development` | Required `CHIRP_SECRET_KEY` |

See `examples/chirpui/lucky_cat/DESIGN.md` §7 and `backplane.py`. Published
copy: [production deployment — demo vs production](https://lbliii.github.io/chirp/docs/quality/deployment/production/).

For framework signals, install `chirp[redis]` and set `CHIRP_REDIS_URL` plus a
shared `CHIRP_SECRET_KEY`. Redis carries rendered live updates at-most-once;
keep the source-of-truth state in an external store for SSR and reconnects.

## Realtime And Compression

SSE is Chirp's realtime contract. Pounce intentionally avoids compressing
`text/event-stream` responses so event delivery is not buffered behind
compression windows.

Pounce can still compress ordinary HTTP responses and WebSocket messages where
that is appropriate. For long-lived Chirp realtime views, tune worker mode and
connection limits before assuming compression is the right lever.

## OpenTelemetry

HTTP request spans are emitted by Pounce when ``AppConfig.otel_endpoint`` is
set (via ``CHIRP_OTEL_ENDPOINT`` in ``AppConfig.from_env()``). Chirp adds
best-effort child spans for AI and tool operations — they no-op when the
OpenTelemetry SDK is not installed:

| Span | Source | Attributes |
|------|--------|------------|
| `llm.generate` | ``chirp.ai.LLM.generate()`` | `provider`, `model`, `duration_ms`, optional `mode=structured` |
| `llm.stream` | ``chirp.ai.LLM.stream()`` | `provider`, `model`, `duration_ms`, `tokens_out` |
| `tool.call` | ``ToolRegistry.call_tool()`` | `tool_name`, `duration_ms`, `error` on failure |

These spans link to the active HTTP span when tools or LLM calls run inside a
route or MCP handler. ``ToolEventBus`` dashboard events still fire alongside
``tool.call`` spans.

Known gap: trace context in manually spawned tasks outside the SSE producer
path is still the caller's responsibility.

Example:

```python
config = AppConfig(
    otel_endpoint="http://otel-collector:4318/v1/traces",
    otel_service_name="my-chirp-app",
)
```

## Pounce Introspection

Pounce 0.7 includes a server-level introspection endpoint at `/_pounce/info`,
but it is disabled by default and remains Pounce-native in Chirp today. Chirp
does not expose `AppConfig` fields for Pounce introspection yet.

If you enable Pounce introspection through `pounce.toml` or `pounce serve`
flags, treat it as an operations endpoint. Pounce handles it before the Chirp
app and before Chirp middleware, so do not rely on Chirp auth, CSRF, sessions,
or allowed-host middleware to protect it.

Bind introspection to loopback or a private admin network, and access it
through a VPN, SSH tunnel, or port-forward. Do not expose it on a public
internet interface.

## Configuration

| Path | Reads | Use For |
|------|-------|---------|
| `AppConfig` | `app.run()` and `chirp run` | Chirp app behavior plus the production server fields Chirp exposes |
| CLI flags to `chirp run` | `chirp run` | Quick overrides for workers, metrics, rate limiting, and request queueing |
| `pounce.toml` | `pounce serve` and `pounce check` | Pounce-native server configuration |
| CLI flags to `pounce serve` | `pounce serve` | Pounce-native server overrides |

Do not assume Pounce environment variable names are read by Chirp. If your
platform provides deployment variables, read them in your app code and build an
`AppConfig`, or start through `pounce serve --config pounce.toml`.

Chirp intentionally does not expose Pounce trusted proxy, compression, or
introspection settings through `AppConfig` yet. Those fields are
security-facing and need a separate public API decision before adoption.

## Security Checklist

- Set `debug=False` in production.
- Use a strong `secret_key` generated with `secrets.token_urlsafe()`.
- Run `chirp check myapp:app --deploy`.
- Run `pounce check --app myapp:app` with your production server config.
- Set explicit `allowed_hosts`; wildcard hosts are reported by `app.check()`
  outside development.
- Add `SecurityHeadersMiddleware` or equivalent headers through custom
  middleware.
- Add `CSRFMiddleware` for apps with POST, PUT, PATCH, or DELETE forms.
- Never use `| safe` on user input without sanitization.
- Enable TLS with valid certificates.
- Enable rate limiting where public traffic can reach the app, and only trust
  `X-Forwarded-For` behind a proxy that rewrites it.
- Set appropriate CORS policies; credentialed CORS requires explicit origins.
- Monitor metrics and health checks.
- Configure graceful shutdown timeouts for your deployment platform.

## Next Steps

- Configure CI/CD preflight checks.
- Load test your application with production-like worker settings.
- Document runbooks for operations and incident response.
- See the published deployment guide at
  <https://lbliii.github.io/chirp/docs/quality/deployment/production/>.

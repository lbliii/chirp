---
title: Production Deployment
description: Deploy Chirp apps with Pounce Phase 5 & 6 features
draft: false
weight: 10
lang: en
type: doc
tags: [production, pounce, docker, metrics, rate-limit]
keywords: [deploy, production, pounce, workers, metrics, rate-limit, docker, port, SO_REUSEADDR, TIME_WAIT, CLI]
category: guide
---

## Overview

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), a production-grade ASGI server with enterprise features built-in.

### Phase 5 (Automatic)

- **HTTP response and WebSocket compression** — ordinary responses and WebSocket messages can be compressed; Pounce intentionally avoids compressing `text/event-stream`
- **HTTP/2 support** — Multiplexed streams, server push
- **Graceful shutdown** — Finishes active requests on SIGTERM
- **Zero-downtime reload** — `kill -SIGUSR1` for hot code updates
- **OpenTelemetry** — Distributed tracing (configurable)

### Phase 6 (Configurable)

- **Prometheus metrics** — `/metrics` endpoint for monitoring
- **Per-IP rate limiting** — Token bucket algorithm
- **Request queueing** — Load shedding during traffic spikes
- **Sentry integration** — Error tracking and reporting
- **Hot reload** — Zero-downtime worker replacement

## Quick Start

### Development Mode

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))

@app.route("/")
def index():
    return "Hello!"

app.run()  # Single worker, auto-reload
```

### Production Mode

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
    return "Hello, Production!"

app.run()  # Multi-worker, Phase 5 & 6 features
```

### CLI Production Mode

```bash
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

## Operator Preflight

Run Chirp and Pounce checks before deployment because they validate different
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
file, bind address, TLS files, worker settings, and related server options. If
you do not use `pounce.toml`, pass the same server flags you use at runtime:

```bash
pounce check --app myapp:app --host 0.0.0.0 --port 8000 --workers 4
```

## Pounce-Native Config

`pounce.toml` is Pounce-native today. It is read by `pounce serve` and
`pounce check`; it is not read by `app.run()` or `chirp run`, which use
`AppConfig` plus Chirp CLI flags.

```bash
pounce config schema --output-format toml-template
pounce config schema --output-format json
pounce config show --config pounce.toml --output-format toml
pounce serve --app myapp:app --config pounce.toml
```

Use `toml-template` to generate a starting `pounce.toml`, `json` for tooling,
and `config show` to inspect the resolved Pounce config after file and CLI
overrides are merged.

## Worker Lifecycle Hooks

Use `@app.on_worker_startup` and `@app.on_worker_shutdown` for resources that
must be created inside each production worker, such as async HTTP clients or
event-loop-bound database pools.

Worker lifecycle hooks require async workers in production:

```python
config = AppConfig(debug=False, workers=4, worker_mode="async")
```

Pounce 0.7 sync workers do not emit worker lifecycle scopes. On free-threaded
Python, Pounce resolves `worker_mode="auto"` to sync workers, so Chirp rejects
production launch when worker hooks are registered and the effective worker
mode is sync. If you do not register worker hooks, `worker_mode="auto"` remains
valid.

Worker startup failures are best-effort in Pounce 0.7 async workers: Pounce
logs the exception and continues serving. Put must-succeed application-wide
checks in `@app.on_startup`, and use a health check for dependencies that can
fail after startup. Fail-loud worker startup is tracked upstream in
[pounce#65](https://github.com/lbliii/pounce/issues/65).

## Realtime And Compression

SSE is Chirp's realtime contract. Pounce intentionally avoids compressing
`text/event-stream` responses so event delivery is not buffered behind
compression windows. Use `worker_mode="async"` for apps with long-lived SSE
connections.

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

## Custom Port Checks

If your CLI checks whether a port is free before calling `app.run()` (e.g. to avoid split-brain or show a clearer error), use `SO_REUSEADDR` in that check. Otherwise you'll block restarts when the port is in **TIME_WAIT** (30–120 seconds after shutdown). The server already uses `SO_REUSEADDR`; your check should match.

```python
import socket

def is_port_in_use(host: str, port: int) -> bool:
    """Return True if another process is actively listening on host:port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
    except OSError:
        return True
```

Without `SO_REUSEADDR`, the check fails when the port is in TIME_WAIT even though the server would bind successfully. When you can't identify the process holding the port, include a TIME_WAIT hint in your error message (e.g. "wait 30–60s or use a different port").

## Docker

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY . .
RUN pip install bengal-chirp
CMD ["chirp", "run", "myapp:app", "--production", "--workers", "4"]
```

## Configuration

| Config | Default | Description |
|--------|---------|-------------|
| `workers` | `0` (auto) | Worker count (0 = CPU count) |
| `worker_mode` | `"auto"` | Pounce worker execution mode; use `"async"` when registering worker lifecycle hooks |
| `metrics_enabled` | `False` | Prometheus `/metrics` endpoint |
| `rate_limit_enabled` | `False` | Per-IP rate limiting |
| `request_queue_enabled` | `False` | Request queueing and load shedding |
| `sentry_dsn` | `None` | Sentry error tracking |
| `ssl_certfile` | `None` | TLS certificate (enables HTTP/2) |
| `ssl_keyfile` | `None` | TLS private key |

Do not assume Pounce environment variable names are read by Chirp. If your
platform provides deployment variables, read them in your app code and build an
`AppConfig`, or start through `pounce serve --config pounce.toml`.

Chirp does not yet expose Pounce compression or introspection settings through
`AppConfig`; those remain security-facing decisions deferred to a later public
API pass. Reverse-proxy trust **is** now exposed — see below.

## Running Behind A Reverse Proxy

When Chirp runs behind a reverse proxy (nginx, a load balancer, a CDN, a
platform router), the socket peer is the proxy, not the end user. The real
client IP arrives in the `X-Forwarded-For` header. Two `AppConfig` fields
control how that header is trusted; both thread through to pounce's
`ServerConfig`.

| Field | Default | Effect |
|-------|---------|--------|
| `trusted_proxies` | `()` | Reverse-proxy peer IPs/hostnames whose `X-Forwarded-For` is honored (maps to pounce `ServerConfig.trusted_hosts`). |
| `forwarded_for_trusted_hops` | `1` | Trailing `X-Forwarded-For` hops to trust when deriving the client IP. Must be `>= 1`. |

```python
config = AppConfig(
    env="production",
    secret_key="...",
    trusted_proxies=("10.0.0.1", "10.0.0.2"),  # your proxy peers
    forwarded_for_trusted_hops=1,               # one proxy in front of the app
)
```

**`X-Forwarded-For` is ignored unless `trusted_proxies` is set.** With the empty
default, Chirp does not trust forwarded headers at all and the request client IP
is the raw socket peer (the proxy). This is the safe default: it cannot be
spoofed. Set `trusted_proxies` only once you know the IPs/hostnames of the
proxies actually in front of your app — `forwarded_for_trusted_hops` only takes
effect when the direct peer is one of those trusted proxies.

**Do not set `forwarded_for_trusted_hops=0` to "disable" forwarding** — it must
be `>= 1` and `AppConfig` raises `ConfigurationError` at construction otherwise
(pounce rejects it at launch). To ignore `X-Forwarded-For`, leave
`trusted_proxies` empty.

**The `"*"` wildcard trusts every direct peer's `X-Forwarded-For`**, which lets
any client spoof its client IP — defeating per-IP rate limiting and skewing
audit correlation. Use it only on a fully locked-down network where the only
reachable peers are your own proxies. The `trusted_proxies` contract check emits
a `WARNING` whenever `trusted_proxies` contains `"*"` outside development (see
the [category reference](/chirp/docs/quality/contracts-debugging/categories/)).

Do **not** set pounce's `trusted_hosts_wildcard` directly — pounce derives it
from `"*"` membership in `trusted_hosts`.

### Access-log vs client-IP divergence

Be aware these two values can disagree:

- **Pounce access logs** key on the **raw socket peer IP** (the proxy).
- **The per-IP rate limiter and the request client IP** (`request.client`) use
  the **rewritten `X-Forwarded-For` client IP** — but only when the direct peer
  is a trusted proxy. When `trusted_proxies` is empty, both reflect the raw peer.

Do not build audit or correlation logic that assumes the access-log peer IP and
the rate-limiter/request client IP are the same value. Behind a trusted proxy
they intentionally differ.

## Full Guide

For detailed deployment instructions, TLS setup, Kubernetes, and advanced configuration, see the source for this published guide in the repository:

**[site/content/docs/quality/deployment/production.md](https://github.com/lbliii/chirp/blob/main/site/content/docs/quality/deployment/production.md)**

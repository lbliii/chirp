---
title: Production Deployment
description: Ship a Chirp app to production on Pounce — prod AppConfig, the deploy preflight, workers, metrics, rate limiting, and reverse-proxy trust.
draft: false
weight: 10
lang: en
type: doc
tags: [production, pounce, docker, metrics, rate-limit]
keywords: [deploy, production, pounce, workers, metrics, rate-limit, docker, reverse-proxy, trusted_proxies, CLI]
category: guide
---

## What this page is

A Chirp app deploys as a single [ASGI](https://asgi.readthedocs.io/) app served by [Pounce](https://github.com/lbliii/pounce), Chirp's production server. There is one server and one app — no separate API tier, no worker queue to stand up.

In development you run one auto-reloading worker. In production you turn on multiple workers, metrics, and rate limiting, wire the secure-by-default stack, and gate the deploy on a contract preflight. This page is the operator's path from a working app to a hardened launch.

Reach for it when you are shipping. For what the contract checks actually enforce, see the [[docs/quality/contracts-debugging/categories|contract category reference]]; for the full server-flag and freeze map, see the [[docs/quality/deployment/_index|deployment overview]].

## Configure the app

The only difference between dev and prod is `AppConfig`. Pick the form you run with — all three start the same app.

:::{tab-set}
:::{tab-item} Development
Single worker, auto-reload, debug error pages. No secret needed while `env="development"`.

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))

@app.route("/")
def index():
    return "Hello!"

app.run()  # single worker, auto-reload
```
:::{/tab-item}
:::{tab-item} Production (Python)
Multiple workers, metrics, and rate limiting. `env="production"` turns on the env-aware safety severities, and the secret is read from the environment — never hard-coded.

```python
import os
from chirp import App, AppConfig

config = AppConfig(
    env="production",
    debug=False,
    secret_key=os.environ["CHIRP_SECRET_KEY"],
    workers=4,
    metrics_enabled=True,
    rate_limit_enabled=True,
)

app = App(config=config)

@app.route("/")
def index():
    return "Hello, production!"

app.run()  # multi-worker
```
:::{/tab-item}
:::{tab-item} CLI
Skip the Python wiring and pass production flags on the command line. The CLI reads `CHIRP_SECRET_KEY` from the environment.

```bash
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```
:::{/tab-item}
:::{/tab-set}

`AppConfig.from_env()` reads `CHIRP_*` environment variables for you, so you can keep config out of code entirely:

```python
config = AppConfig.from_env(env="production", worker_mode="async")
```

:::{danger}
Never ship a literal secret in your source. `secret_key` signs sessions and CSRF tokens; a committed value is a published key.

Read it from the environment (`os.environ["CHIRP_SECRET_KEY"]` or `AppConfig.from_env()`). `AppConfig` raises `ConfigurationError` at construction when `secret_key` is empty and `env` is not `"development"`, so a misconfigured prod app fails fast instead of running with no signing key.
:::

## Deploy

::::{steps}
:::{step} Set the secret and a production config

Export `CHIRP_SECRET_KEY` in the deploy environment and build a production `AppConfig` with `env="production"` (see the tabs above). The `env` value drives the deploy severities in the next step.
:::{/step}

:::{step} Run the preflight

Run both checks before every deploy — they validate different contracts:

```bash
chirp check myapp:app --deploy
pounce check --app myapp:app --config pounce.toml
```

`chirp check --deploy` answers "would this app pass `app.check()` with `env="production"`?" without mutating your config — it builds a throwaway production-posture view and re-runs the env-aware safety rules (`secret_key`, `allowed_hosts`, `security_stack`, `csp_nonce`, and the `debug`/`metrics`/`sentry` posture). `--deploy` implies `--warnings-as-errors`, so warnings fail the build. A deploy-ready app still passes — the check is tighten-only. Wire it as your CI deploy gate.

`pounce check` validates Pounce's server-facing inputs: import path, bind address, TLS files, and worker settings. If you do not use `pounce.toml`, pass the same flags you run with:

```bash
pounce check --app myapp:app --host 0.0.0.0 --port 8000 --workers 4
```
:::{/step}

:::{step} Launch

Start the production server — multi-worker, with the features you enabled:

```bash
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

Or build the image and let the container run it:

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY . .
RUN pip install bengal-chirp
CMD ["chirp", "run", "myapp:app", "--production", "--workers", "4"]
```
:::{/step}
::::{/steps}

:::{note}
Use `chirp check --warnings-as-errors` (without `--deploy`) when you want strict warnings but do not want to escalate the production-only severities — for example, on a staging gate.
:::

## What the server gives you

Pounce handles these for every Chirp app, no configuration required:

- HTTP and WebSocket compression — ordinary responses are compressed; `text/event-stream` is left uncompressed so [[docs/build-apps/streaming-updates/server-sent-events|SSE]] events are not buffered behind a compression window.
- HTTP/2 with multiplexed streams (enabled when you set `ssl_certfile`/`ssl_keyfile`).
- Graceful shutdown — active requests finish on `SIGTERM`.
- Mode-scoped rolling reload — send `SIGHUP` to replace thread-worker generations while old
  requests drain. Single-worker, process-worker, subinterpreter, and HTTP/3 behavior differs;
  review [Pounce's current lifecycle matrix](https://github.com/lbliii/pounce/blob/main/docs/design/core-contract.md#lifecycle-mode-matrix)
  before treating a reload as lossless.
- OpenTelemetry distributed tracing (configurable).

These you opt into through `AppConfig` or CLI flags:

:::{list-table}
:header-rows: 1

* - Field
  - Default
  - What it does
* - `workers`
  - `0` (auto)
  - Worker count; `0` resolves to the CPU count.
* - `worker_mode`
  - `"auto"`
  - Pounce worker execution mode; use `"async"` when you register worker lifecycle hooks.
* - `metrics_enabled`
  - `False`
  - Prometheus endpoint at `/metrics`.
* - `rate_limit_enabled`
  - `False`
  - Per-IP rate limiting (token bucket).
* - `request_queue_enabled`
  - `False`
  - Request queueing and load shedding under traffic spikes.
* - `sentry_dsn`
  - `None`
  - Sentry error tracking.
* - `ssl_certfile` / `ssl_keyfile`
  - `None`
  - TLS certificate and key (enables HTTP/2).
:::

For every `AppConfig` field, see [[docs/about/core-concepts/configuration|Configuration]].

:::{note}
Chirp does not read Pounce's own environment variable names. If your platform injects deploy variables, read them in your app code and build an `AppConfig`, or start through `pounce serve --config pounce.toml`.
:::

## Health and readiness probes

Chirp auto-mounts two ops endpoints — no hand-wiring, present on every app including the `chirp new --minimal` scaffold:

- **`/health`** (liveness) — always returns plain `200 ok`. Wire it to a Kubernetes `livenessProbe`: if it stops answering, the orchestrator restarts the pod.
- **`/ready`** (readiness) — returns `503` until startup completes (db connect, migrations, and every `@app.on_startup` hook), then runs every registered readiness check. If a check fails it returns `503` plus the failure list; otherwise plain `200 ready`. Wire it to a `readinessProbe` so the pod is pulled from the load-balancer rotation while it is starting up, draining on shutdown, or a dependency is down.

Both probes **bypass the secure middleware stack** (Session/CSRF/SecurityHeaders) and the commit teardown — they run no user handler, set no cookie, and never touch the session — and return plain `200`/`503` text outside Chirp's return-type negotiation.

Change the paths with `AppConfig(health_path=..., ready_path=...)` or `CHIRP_HEALTH_PATH` / `CHIRP_READY_PATH`. A user route claiming a probe path wins (the probe steps aside); `app.check()` flags the collision as a `deploy_health` ERROR so it never happens silently.

Register dependency checks before freeze:

```python
from chirp import HealthCheck

app.add_health_check(HealthCheck("cache", check=ping_cache))   # sync or async
```

When a database is wired, Chirp auto-includes a `Database.probe()`-backed check (a `SELECT 1` on a **fresh pooled connection**, never the request session), so `/ready` reflects DB connectivity for free.

A Kubernetes deployment wires them like this:

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8000 }
readinessProbe:
  httpGet: { path: /ready, port: 8000 }
```

## Wire the secure-by-default stack

A production app with any mutating route must wire `SessionMiddleware` → `CSRFMiddleware` → `SecurityHeadersMiddleware`. Chirp does not inject these for you; `chirp check --deploy` fails when they are missing in production. Every `chirp new` scaffold wires them out of the box.

The full stack, ordering rules, and CSRF form patterns live on [[docs/quality/deployment/auth-hardening|Auth Hardening]] — wire it before you go live.

## Run behind a reverse proxy

When Chirp runs behind a proxy (nginx, a load balancer, a CDN, a platform router), the socket peer is the proxy, not the end user. The real client IP arrives in the `X-Forwarded-For` header. Two `AppConfig` fields control how that header is trusted:

:::{list-table}
:header-rows: 1

* - Field
  - Default
  - Effect
* - `trusted_proxies`
  - `()`
  - Reverse-proxy peer IPs/hostnames whose `X-Forwarded-For` is honored. Maps to Pounce's `ServerConfig.trusted_hosts`.
* - `forwarded_for_trusted_hops`
  - `1`
  - Trailing `X-Forwarded-For` hops to trust when deriving the client IP. Must be `>= 1`.
:::

```python
config = AppConfig(
    env="production",
    secret_key=os.environ["CHIRP_SECRET_KEY"],
    trusted_proxies=("10.0.0.1", "10.0.0.2"),  # your proxy peers
    forwarded_for_trusted_hops=1,               # one proxy in front of the app
)
```

:::{warning}
`X-Forwarded-For` is ignored entirely until you set `trusted_proxies`. The empty default is the safe one: the request client IP is the raw socket peer, which cannot be spoofed.

The `"*"` wildcard trusts every direct peer's `X-Forwarded-For`, which lets any client spoof its client IP — defeating per-IP rate limiting and skewing audit correlation. Use it only on a locked-down network where the only reachable peers are your own proxies. The `trusted_proxies` contract check emits a `WARNING` for `"*"` outside development.
:::

`forwarded_for_trusted_hops` only takes effect when the direct peer is one of your `trusted_proxies`. To ignore `X-Forwarded-For`, leave `trusted_proxies` empty — do not set the hop count to `0`. It must be `>= 1`, and `AppConfig` raises `ConfigurationError` at construction otherwise.

## Realtime workloads

[[docs/build-apps/streaming-updates/server-sent-events|SSE]] is Chirp's realtime contract. Pounce intentionally avoids compressing `text/event-stream` responses so event delivery is not buffered behind a compression window. Use `worker_mode="async"` for apps with long-lived SSE connections.

### Demo tier vs production tier

Some examples (notably [[docs/examples/lucky-cat|Lucky Cat]]) pin `workers=1` and
keep wallet, trades, notifications, and the signal bus in process memory so they
clone-and-run offline. That is a **demo boundary**, not a framework ceiling.

| Concern | Demo (in-memory example) | Production |
|---------|--------------------------|------------|
| Workers | `1` | `N` with a shared signal backplane |
| State | In-process stores | External source of truth (DB/Redis) |
| Signal fan-out | `InProcessBackplane` | Shared bus (e.g. Redis — see signal RFC §12) |
| Secret | Dev fallback in `development` | Required `CHIRP_SECRET_KEY` |

Multi-worker production needs both external state **and** a shared backplane so
`/_chirp/live` connections and `app.emit` fan-out stay coherent across processes.
See the Lucky Cat `DESIGN.md` §7 and `backplane.py` seam for the worked example.

## Advanced

:::{dropdown} Worker lifecycle hooks and async workers
Use `@app.on_worker_startup` and `@app.on_worker_shutdown` for resources that must be created inside each production worker — async HTTP clients or event-loop-bound database pools.

```python
config = AppConfig(debug=False, workers=4, worker_mode="async")
```

Worker lifecycle hooks require async workers in production. On free-threaded Python, `worker_mode="auto"` resolves to sync workers, which do not emit worker lifecycle scopes — so Chirp rejects production launch when worker hooks are registered and the effective mode is sync. If you do not register worker hooks, `worker_mode="auto"` stays valid.
:::{/dropdown}

::::{dropdown} Worker startup failure semantics
A worker-startup exception is logged and the worker keeps serving — startup failures do not currently abort the launch. Put must-succeed, application-wide checks in `@app.on_startup`, and use a health check for dependencies that can fail after startup.

:::{changed} Pounce 0.7
Worker startup is best-effort in Pounce 0.7 async workers (logged, not fatal). Fail-loud worker startup is tracked upstream.
:::
::::{/dropdown}

:::{dropdown} pounce.toml — server-native config
`pounce.toml` is read by `pounce serve` and `pounce check`. It is not read by `app.run()` or `chirp run`, which use `AppConfig` plus Chirp CLI flags.

```bash
pounce config schema --output-format toml-template   # generate a starting file
pounce config schema --output-format json            # for tooling
pounce config show --config pounce.toml               # inspect the resolved config
pounce serve --app myapp:app --config pounce.toml
```
:::{/dropdown}

:::{dropdown} Pounce introspection endpoint
Pounce ships a server-level introspection endpoint at `/_pounce/info`, disabled by default and Pounce-native — Chirp does not expose an `AppConfig` field for it.

If you enable it through `pounce.toml` or `pounce serve` flags, treat it as an operations endpoint. Pounce serves it before the Chirp app and before Chirp middleware, so Chirp auth, CSRF, sessions, and allowed-host middleware do not protect it. Bind it to loopback or a private admin network and reach it through a VPN, SSH tunnel, or port-forward. Do not expose it on a public internet interface.
:::{/dropdown}

:::{dropdown} Access logs vs. client IP can disagree
Two values can disagree behind a proxy, by design:

- **Pounce access logs** key on the raw socket peer IP (the proxy).
- **The per-IP rate limiter and `request.client`** use the rewritten `X-Forwarded-For` client IP — but only when the direct peer is a trusted proxy. With `trusted_proxies` empty, both reflect the raw peer.

Do not build audit or correlation logic that assumes the access-log peer IP and the rate-limiter/request client IP are the same value.
:::{/dropdown}

:::{dropdown} Free a port without blocking on TIME_WAIT
If your own CLI checks whether a port is free before calling `app.run()`, use `SO_REUSEADDR` in that check. Otherwise the check fails while the port sits in `TIME_WAIT` (30–120s after shutdown) even though the server would bind successfully. The server already sets `SO_REUSEADDR`; match it.

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
:::{/dropdown}

:::{note} See also
- [[docs/quality/deployment/auth-hardening|Auth Hardening]] — wire the secure-by-default stack before launch
- [[docs/quality/contracts-debugging/categories|Contract categories]] — what each `chirp check` rule enforces
- [[docs/about/core-concepts/configuration|Configuration]] — every `AppConfig` field
- [[docs/quality/deployment/_index|Deployment overview]] — server flags and freeze-vs-serve map
:::

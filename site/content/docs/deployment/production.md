---
title: Production Deployment
description: Deploy Chirp apps with Pounce Phase 5 & 6 features
draft: false
weight: 10
lang: en
type: doc
tags: [production, pounce, docker, metrics, rate-limit]
keywords: [deploy, production, pounce, workers, metrics, rate-limit, docker]
category: guide
---

## Overview

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), a production-grade ASGI server with enterprise features built-in.

### Phase 5 (Automatic)

- **WebSocket compression** — 60% bandwidth reduction
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
| `metrics_enabled` | `False` | Prometheus `/metrics` endpoint |
| `rate_limit_enabled` | `False` | Per-IP rate limiting |
| `request_queue_enabled` | `False` | Request queueing and load shedding |
| `sentry_dsn` | `None` | Sentry error tracking |
| `ssl_certfile` | `None` | TLS certificate (enables HTTP/2) |
| `ssl_keyfile` | `None` | TLS private key |

## Full Guide

For detailed deployment instructions, TLS setup, Kubernetes, and advanced configuration, see the full deployment guide in the repository:

**[docs/deployment/production.md](https://github.com/lbliii/chirp/blob/main/docs/deployment/production.md)**

---
title: Deployment
description: Production deployment, Pounce, Docker, Kubernetes, metrics, and runtime configuration
draft: false
weight: 30
lang: en
type: doc
tags: [deployment, production, pounce, docker, operations]
keywords: [deploy, production, pounce, docker, metrics, rate-limit]
category: guide
icon: server

cascade:
  type: doc
---

## Production with Pounce

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), a production-grade ASGI server with enterprise features built-in.

:::{cards}
:columns: 2
:gap: medium

:::{card} Production Deployment
:icon: server
:link: /chirp/docs/quality/deployment/production/
:description: Full guide to deploying Chirp in production
Phase 5 & 6 features, Docker, Kubernetes, and configuration.
:::{/card}

:::{card} Hybrid Static + App Deployment
:icon: split
:link: /chirp/docs/quality/deployment/freeze-hybrid/
:description: Freeze public pages, serve interactive routes
Combine static output with a live Chirp app where that split is useful.
:::{/card}

:::{card} Auth Hardening
:icon: shield
:link: /chirp/docs/quality/deployment/auth-hardening/
:description: Production checklist for auth and authz
Harden sessions, CSRF, abuse limits, security headers, and audit events.
:::{/card}

:::{/cards}

## Quick Start

```bash
# Development (single worker, auto-reload)
chirp run myapp:app

# Production (multi-worker, all features)
chirp run myapp:app --production --workers 4 --metrics --rate-limit

# Production preflight
chirp check myapp:app --warnings-as-errors
pounce check --app myapp:app --host 0.0.0.0 --port 8000 --workers 4
```

Or from Python:

```python
from chirp import App, AppConfig

config = AppConfig(debug=False, secret_key="...")
app = App(config=config)

# app.run() uses production server when debug=False
app.run()
```

`pounce.toml` is Pounce-native today. Use it with `pounce serve --app
myapp:app --config pounce.toml`; `app.run()` and `chirp run` use `AppConfig`
and Chirp CLI flags.

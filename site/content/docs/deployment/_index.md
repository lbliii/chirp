---
title: Deployment
description: Deploy Chirp apps in production with Pounce
draft: false
weight: 95
lang: en
type: doc
tags: [deployment, production, pounce, docker]
keywords: [deploy, production, pounce, docker, metrics, rate-limit]
category: guide
icon: server

cascade:
  type: doc
---

## Production with Pounce

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), a production-grade ASGI server with enterprise features built-in.

:::{card} Production Deployment
:link: ./production
:description: Full guide to deploying Chirp in production
Phase 5 & 6 features, Docker, Kubernetes, and configuration.
:::{/card}

## Quick Start

```bash
# Development (single worker, auto-reload)
chirp run myapp:app

# Production (multi-worker, all features)
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

Or from Python:

```python
from chirp import App, AppConfig

config = AppConfig(debug=False, secret_key="...")
app = App(config=config)

# app.run() uses production server when debug=False
app.run()
```

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

## Ship a Chirp app to production

Ship a Chirp app and keep it healthy: pick the right server flags, decide what to freeze versus serve live, and harden auth before you go live. Chirp apps run on Pounce, a production ASGI server (see [[docs/quality/deployment/production|Production Deployment]] below).

:::{child-cards}
:::

The smallest production command — multi-worker, with metrics and rate limiting:

```bash
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

:::{tip}
Gate the deploy on the contract preflight: run `chirp check myapp:app --warnings-as-errors` in CI before you release. The [[docs/quality/contracts-debugging/categories|contract categories]] explain what each check enforces, and [[docs/quality/deployment/production|Production Deployment]] has the full command, config, and CI setup.
:::

:::{note}
Server config files (`pounce.toml`) and the Python `app.run()` form are covered on the [[docs/quality/deployment/production|Production Deployment]] page. `app.run()` and `chirp run` read `AppConfig`; a `pounce.toml` is read by Pounce's own CLI.
:::

:::{note} See also
- [[docs/quality/_index|Quality and Operations]] — back to the quality overview
- [[docs/quality/deployment/auth-hardening|Auth Hardening]] — secure-by-default wiring before launch
:::

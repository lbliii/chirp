---
title: Non-Goals
description: The bright lines Chirp will not cross — what the core deliberately won't do, and the honest alternative for each
draft: false
weight: 35
lang: en
type: doc
tags: [non-goals, identity, scope, philosophy]
keywords: [non-goals, scope, identity, stateless, no orm, no websocket, asgi, free-threading]
category: explanation
---

## Overview

Chirp is an application framework for server-rendered Python UIs, not a
kitchen-sink application platform. It deliberately leaves some jobs to other
tools — an ORM, background jobs, WebSockets, an admin generator — and pairs
every "no" with the tool you would reach for instead. This page is the honest
map of those bright lines so you can decide whether Chirp fits.

Every non-goal protects one property: the server holds **zero per-client view
state**. A request renders HTML from data fetched for that request, and the
server keeps nothing about *that client's screen* between requests — no
server-held component tree, no session-bound view graph, no per-connection UI
model. That is why there is structurally nothing for two threads to race over
under free-threading (see [[docs/about/thread-safety|why zero view state matters under 3.14t]]).

## What Chirp will not do — and what to do instead

The table is the whole answer. Each row is a deliberate bright line plus the tool
you would reach for in its place.

::::{list-table}
:header-rows: 1

* - Chirp won't…
  - Why
  - Reach for instead
* - **Ship a stateful ORM**
  - Sessions, identity maps, and lazy loading reintroduce hidden I/O and per-client mutable state.
  - [[docs/build-apps/forms-data/shapes|Shapes]] (SQL in, frozen dataclasses out), or SQLAlchemy / SQLModel / raw SQL.
* - **Generate an admin / CRUD UI**
  - Core's job is content negotiation and rendering, not a generated UI most apps outgrow.
  - Compose [[docs/about/core-concepts/return-values|return types]] and chirp-ui components into list/detail/edit flows you own.
* - **Embed email / SMTP**
  - Delivery is a separate operational concern with its own retries and providers.
  - Render the body as a Kida template, hand the HTML to a bring-your-own mailer (SES, Postmark, Resend, SMTP).
* - **Run background jobs**
  - Task queues need their own durability, retry, and observability.
  - Celery, RQ, Dramatiq, or your platform scheduler — Chirp owns only the progress surface ([[docs/build-apps/streaming-updates/html-streaming|Suspense]] / [[docs/build-apps/streaming-updates/server-sent-events|EventStream]]).
* - **Add a WebSocket return type**
  - Almost every "real-time" feature is server-push, which SSE already covers over plain HTTP.
  - [[docs/build-apps/streaming-updates/server-sent-events|EventStream / SSE]] for server-push; raw WebSockets live below the framework at the ASGI server.
* - **Support WSGI or a lower Python floor**
  - The thread-safety story depends on the free-threaded Python 3.14 build.
  - Generic ASGI — Chirp runs on any conforming ASGI server, not one vendor.
* - **Own general HTTP rate limiting**
  - Global throttling, IP reputation, and DDoS shaping see traffic Chirp never does.
  - Your proxy / CDN edge (nginx, Cloudflare, gateway). Chirp ships only auth-path lockout.
* - **Become a telemetry / APM product**
  - Observability backends are a market Chirp does not compete in.
  - Wire Prometheus, Sentry, or OpenTelemetry through config; bring your own backend.
* - **Absorb a Django-sized ecosystem**
  - Chasing breadth dilutes the rendering-layer focus.
  - A small, verifiable surface plus a stable [[docs/quality/contracts-debugging/categories|custom contract checks]] protocol so the ecosystem grows *around* a stable core.
::::

:::{since} 0.8
The data-layer alternative to an ORM — [[docs/build-apps/forms-data/shapes|Shapes]]
(`@shape` / `Shape` / `nested` / `@composite`, the `shapecheck` contract, and the
`chirp shapes-codegen` CLI) — shipped in the 0.8 cycle. It is the "SQL in, frozen
dataclasses out" path referenced in the first row above.
:::

::::{dropdown} How the escape hatches work
:icon: wrench
Each "instead" above has a real seam in Chirp. The detail below is for the
practitioner wiring one of these boundaries; you can score the table without it.

**Data layer.** `Database.fetch` returns typed, frozen dataclasses mapped from
rows — data flows toward the screen, fetched for purpose, immutable. The
field-level SQL-to-render contract is [[docs/build-apps/forms-data/shapes|Shapes]];
the connection and query mechanics are the [[docs/build-apps/forms-data/database|database layer]].

**Background fan-out.** For database-driven updates, `Database.listen()` pairs
PostgreSQL `LISTEN/NOTIFY` with [[docs/build-apps/streaming-updates/server-sent-events|EventStream]]
so a worker running elsewhere can push HTML updates — Chirp streams them without
owning the worker.

**Raw WebSockets.** If you genuinely need bidirectional WebSockets, the ASGI
server handles the connection directly. The Pounce pass-through exposes knobs like
`websocket_compression` and `websocket_max_message_size` on `AppConfig`. Chirp
does not negotiate a return type into a WebSocket frame.

**Auth-path rate limiting.** Chirp ships only the lockout that must live next to
the login decision: `LoginLockout` primitives and `AuthRateLimitMiddleware`
(`chirp.middleware`), with pluggable backends for cross-worker lockout. Everything
broader stays at the edge. See [[docs/quality/deployment/auth-hardening|auth hardening]].

**Telemetry.** Telemetry is a config surface, not a bundled backend: `metrics_enabled`
and `metrics_path` for Prometheus, `sentry_dsn` for Sentry, and `otel_endpoint`
for OpenTelemetry. You bring the backend; Chirp emits to it.

**Ecosystem.** `register_contract_check` and the `ContractCheck` protocol let
third-party packages extend `app.check()` with their own validation rules, so
tooling grows around the core rather than inside it.
::::

::::{note} See also

- [[docs/about/philosophy|Philosophy]] — the opinions these bright lines protect, including the SSE-over-WebSocket stance.
- [[docs/about/comparison|When to use Chirp]] — fit, alternatives, and the honest "not for you if…".
- [[docs/about/thread-safety|Thread safety]] — why holding zero view state matters under free-threaded Python 3.14.
::::

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

> **Decision wording pending steward review.** This page states positioning and
> identity bright-lines. The decisions are drafted for human sign-off; the
> *wording* of each "won't do" may still change. The technical claims and code
> references are verified.

## The one-line identity claim

**Chirp holds ZERO per-client server view state.**

Every other line on this page falls out of that one. A request renders HTML from
data fetched for that request, and the server keeps nothing about *that client's
screen* between requests. No server-held component tree, no session-bound view
graph, no per-connection UI model. State lives in the database, in the URL, and
in the DOM — never in a server object that has to be kept in sync with one
browser tab.

This is what lets Chirp be honest about free-threading (Python 3.14t): if the
server holds no mutable per-client view state, there is structurally nothing for
two threads to race over. The non-goals below protect that property.

---

## What Chirp will not do — and what to do instead

Each entry is a deliberate bright line, paired with the honest alternative so
this list is a map, not a wall.

### 1. No stateful ORM

Chirp will not ship an object-relational mapper with a session, an identity map,
lazy loading, or mutable tracked entities. That machinery reintroduces hidden
I/O and per-client mutable state — the precise inverse of the zero-view-state
property above, and a hazard surface under free-threaded 3.14.

**Instead:** a schema-source-of-truth plus *Shapes* — "SQL in, frozen
dataclasses out." `Database.fetch` already returns typed, frozen dataclasses
mapped from rows (`src/chirp/data/database.py:252-309`); data flows *toward the
screen*, fetched for purpose, immutable. The field-level SQL→render contract is
described in the **Shapes RFC** (`plan/drafted/rfc-shapes.md`) — a **Draft RFC,
not shipped**. Use SQLAlchemy, SQLModel, or raw SQL today if you want a
different data layer; Chirp renders HTML regardless of where the data comes
from.

### 2. No in-core admin / CRUD generator

Chirp core will not generate an admin panel or scaffold CRUD screens. The core's
job is content negotiation and rendering, not bundling a generated UI most apps
will outgrow.

**Instead:** a **chirp-ui CRUD cookbook** as the adjacent docs move — recipes
that compose Chirp's own return types (`Page`, `Fragment`, `OOB`,
`ValidationError`) and chirp-ui components into list/detail/edit flows you own.
A schema source-of-truth (see #1) makes this generation *possible* in tooling
without putting a generator in the framework's hot path.

### 3. No in-core email / SMTP

Chirp will not embed an SMTP client, a mail queue, or provider integrations.

**Instead:** render the email body as a Kida template — the same template engine
that renders your pages — and hand the rendered HTML to a **bring-your-own
mailer callback**, the same pattern as `load_user`. Chirp produces the HTML; you
own delivery (SES, Postmark, Resend, your own SMTP).

### 4. No background jobs / scheduler

Chirp will not ship a task queue, a cron/scheduler, or a worker pool. That is a
separate operational concern with its own durability, retry, and observability
needs.

**Instead:** Chirp owns only the **last-mile progress surface** — streaming a
job's progress to the browser via `Suspense` (shell first, deferred blocks) or
`EventStream` (SSE after load). For database-driven fan-out, `Database.listen()`
(`src/chirp/data/database.py:439`) pairs PostgreSQL `LISTEN/NOTIFY` with
`EventStream` so a worker elsewhere can push HTML updates without Chirp owning
the worker. Use Celery, RQ, Dramatiq, or your platform's scheduler for the jobs
themselves.

### 5. No WebSocket return type — SSE over WebSockets, always

Chirp will not add a WebSocket return type. As the
[Philosophy](/chirp/docs/about/philosophy/) puts it: SSE is HTTP — it works
through proxies, load balancers, and CDNs, reconnects automatically, and needs
no protocol upgrade or client library. Almost every "real-time" feature is
server-push, which `EventStream` already covers.

**Instead:** use `EventStream` for server-push. If you genuinely need raw
bidirectional WebSockets, the **Pounce WS pass-through** is the escape hatch —
the underlying ASGI server handles the connection, with knobs like
`websocket_compression` and `websocket_max_message_size`
(`src/chirp/config.py:236-238`). Chirp does not negotiate a return type into a
WebSocket frame; that path lives below the framework.

### 6. No WSGI, and no lowering the Python 3.14 floor

Chirp will not support WSGI and will not drop below Python 3.14. This is the
**free-threading identity bet**: Chirp's thread-safety story (frozen models,
zero per-client view state, structural absence of data races) depends on
3.14-era semantics and the free-threaded build. Synchronous WSGI cannot carry
SSE, streaming, or Suspense without contortions.

**Instead:** Chirp targets **generic ASGI** — it runs on any conforming ASGI
server, not only Pounce, so you are not locked to one deployment. The portability
is at the ASGI boundary, not the WSGI one.

### 7. No general HTTP rate-limiting in core

Chirp will not own general-purpose HTTP rate limiting. Edge concerns — global
request throttling, IP reputation, DDoS shaping — belong at the proxy / CDN edge
(nginx, Cloudflare, your gateway), which sees traffic Chirp never does.

**Instead:** Chirp ships only the **auth-path** rate limiting that must live next
to the login decision: `LoginLockout` primitives
(`src/chirp/security/lockout.py`) and `AuthRateLimitMiddleware`
(`chirp.middleware.auth_rate_limit`), with pluggable backends for cross-worker
lockout. Everything broader stays at the edge.

### 8. No in-core telemetry / APM

Chirp will not become an observability product. It will not ship its own metrics
backend, tracing UI, or APM agent.

**Instead:** telemetry is a **config-surface integration** — Chirp exposes
configuration to wire up Prometheus (`metrics_enabled`, `metrics_path`), Sentry
(`sentry_dsn`, …), and OpenTelemetry (`otel_endpoint`, …) and otherwise gets out
of the way. You bring the backend; Chirp emits to it.

### 9. No ecosystem / hiring absorption into core

Chirp will not try to win by absorbing a Django-sized ecosystem or by being the
framework with the largest hiring pool. Chasing breadth dilutes the sharp
rendering-layer focus.

**Instead:** lean into **AI-buildability** — a small, honest, verifiable surface
that an LLM (and a human) can reason about end to end — and a **stable plugin /
contract protocol** (`register_contract_check`, the `ContractCheck` protocol,
custom severity overrides) so the ecosystem grows *around* a stable core rather
than *inside* it.

---

## See also

- [Philosophy](/chirp/docs/about/philosophy/) — the five opinions these lines protect
- [When to Use Chirp](/chirp/docs/about/comparison/) — fit and alternatives
- [Thread Safety](/chirp/docs/about/thread-safety/) — why zero view state matters under 3.14t

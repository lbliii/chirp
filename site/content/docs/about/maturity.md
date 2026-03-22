---
title: Maturity & Value
description: An honest assessment of where Chirp stands today — what is production-ready, what is still evolving, and what value it delivers
draft: false
weight: 60
lang: en
type: doc
tags: [about, maturity, stability, roadmap]
keywords: [maturity, stability, alpha, production, value, readiness]
category: explanation
---

## Status Snapshot

Chirp is **v0.1.9, Alpha**. The classification is deliberate and honest:

- The API is functional and exercised by 129 test files and ~150 example programs.
- Core contracts (routing, negotiation, fragment rendering, SSE, contracts checker) are
  stable in shape, but breaking changes between minor versions remain possible while
  the framework iterates toward 0.2.
- Production use is possible for teams willing to pin a version and absorb the
  occasional interface adjustment.

---

## Release Velocity

| Version | Date | Milestone |
|---------|------|-----------|
| 0.1.0 | 2026-02-09 | Initial release: routing, templates, SSE, middleware, contracts |
| 0.1.1 | 2026-02-15 | CLI, inline templates, form macros, filesystem routing |
| 0.1.2 | 2026-02-18 | Islands, chirp-ui integration, auth hardening, Alpine.js |
| 0.1.3 | 2026-03-03 | Ongoing hardening |
| 0.1.4 | 2026-03-04 | Enterprise config, health probes, structured logging, Redis sessions |
| 0.1.5 | 2026-03-04 | chirp-ui filter auto-registration |
| 0.1.6 | 2026-03-06 | PageComposition, Suspense + layout chains, kanban_shell example |
| 0.1.7 | 2026-03-10 | App shell guide, islands examples, Alpine macros, breadcrumbs OOB |
| 0.1.8 | 2026-03-10 | Single-source version string |
| 0.1.9 | 2026-03-12 | Route directory contract, sync path, debug introspection, benchmarks |

Ten releases in five weeks signals active iteration, not instability. Each version
adds defined scope and carries a documented changelog entry. The pace reflects a
development phase that is intentionally shipping fast to sharpen the API before
freezing it.

---

## Code Maturity Indicators

### Scale

| Metric | Value |
|--------|-------|
| Source files | 181 Python modules |
| Source lines | ~23,400 |
| Test files | 129 |
| Test lines | ~22,500 |
| Example programs | ~150 |

The test-to-source line ratio is nearly 1:1. That is unusual for Alpha software
and reflects a project that treats tests as a design tool, not an afterthought.

### Coverage Target

`pyproject.toml` enforces `fail_under = 80` branch coverage. The `--strict-markers`
flag and `pytest-xdist` parallelism indicate a test suite that is expected to be fast
and reliable.

### Type Coverage

Chirp targets **zero `type: ignore` comments** and ships a `py.typed` PEP 561 marker.
The type checker (`ty`) is configured to run in strict mode and flag stale ignores.
For an Alpha library this is a strong signal: the public surface is typed, documented,
and machine-checkable.

### Free-Threading Readiness

Chirp is designed for **Python 3.14t** (no-GIL, PEP 703) from the first commit:

- All shared state uses frozen dataclasses (`slots=True`).
- No module-level mutable caches or global dicts.
- Per-request state is isolated via `ContextVar`.
- The GIL-free declaration (`_Py_mod_gil = 0`) is present in the C extension stubs.

This is not a retroactive port. Free-threading safety is structural, not patched.

---

## Feature Completeness

### Stable and Exercised

| Area | Status |
|------|--------|
| Routing (decorator + filesystem) | ✅ Stable |
| Content negotiation (str, dict, Template, Fragment, Stream, SSE, Response, Redirect) | ✅ Stable |
| Kida template integration (fragments, streaming, filters) | ✅ Stable |
| Middleware protocol (CORS, sessions, static files, security headers) | ✅ Stable |
| Contract checker (`app.check()`, `chirp check`) | ✅ Stable |
| CLI (`chirp new`, `chirp run`, `chirp check`, `chirp routes`) | ✅ Stable |
| SSE (`EventStream`, `sse_scope`) | ✅ Stable |
| Testing utilities (`TestClient`) | ✅ Stable |
| Auth helpers (`login`, `logout`, `@login_required`, `@requires`) | ✅ Stable |
| Enterprise config (`AppConfig.from_env`, CHIRP_* env vars) | ✅ Stable |
| Structured logging (JSON + auto format) | ✅ Stable |
| Health probes (`liveness`, `readiness`) | ✅ Stable |

### Evolving

| Area | Status |
|------|--------|
| PageComposition API | 🔄 Settling |
| Route directory contract (`_meta.py`, `_context.py`, sections) | 🔄 Settling |
| App shell patterns (OOB, sidebar, breadcrumbs) | 🔄 Settling |
| Islands contract | 🔄 Settling |
| Sync handler fast path (`handle_sync`, `SyncRequest`) | 🔄 New in 0.1.9 |

### Planned (Unreleased)

The `[Unreleased]` section of `CHANGELOG.md` records the next dependency bumps
(`kida-templates>=0.2.8`, `bengal-pounce>=0.3.1`, `chirp-ui>=0.2.0`) and the
public RFC queue (`proposed/` directory) contains active proposals for:

- ASGI lifespan hooks
- Implicit fragment resolution
- Component collections
- Per-worker hooks
- SSE scope stability

---

## Value Assessment

### The Gap Chirp Fills

No mature Python framework has made **HTMX-first, HTML-over-the-wire** its
primary abstraction. Flask and FastAPI support Jinja templates as a side concern.
Django's template layer predates htmx by many years. Chirp starts from the
premise that fragments, OOB swaps, and SSE are the primary delivery channel,
not an add-on.

The result is a set of capabilities that require significant assembly work in
any other Python framework:

- `Page` returns a fragment or full page based on the `HX-Request` header — one
  return value, two behaviors, zero branching in handler code.
- `app.check()` validates every `hx-get`, `hx-post`, `hx-target`, `action`, and
  `sse-connect` attribute against the registered route table at startup.
- Fragment rendering is a first-class return type — the template engine knows
  which block to render without a separate partial template.
- `EventStream` + Kida-rendered fragments deliver real-time HTML with no
  client-side JavaScript required beyond htmx.

### Minimal Dependency Surface

Chirp's core requires three packages:

```
kida-templates  — Template engine (same ecosystem)
anyio           — Backend-agnostic async runtime
bengal-pounce   — Production ASGI server
```

Everything else — form parsing, session signing, password hashing, Redis,
database access, markdown, UI components — is optional and explicitly gated
behind extras. An application that does not need session state does not pay for
`itsdangerous`.

### Production Deployment Story

Chirp ships on **Pounce**, a production-grade ASGI server with:

- HTTP/2 multiplexing
- WebSocket compression (60% bandwidth reduction)
- Graceful shutdown on SIGTERM
- Zero-downtime reload via SIGUSR1
- Built-in `/health` endpoint for Kubernetes liveness/readiness
- Optional Prometheus `/metrics`, per-IP rate limiting, and Sentry integration

Zero additional infrastructure is required to run Chirp in production. One `pip install`
covers the framework and its server.

### Free-Threading Advantage

Python 3.14t removes the GIL. Chirp was designed for this from the start.
Frameworks designed before free-threading will need structural changes (audit
and replace every global dict, every module-level cache) to be safe. Chirp's
immutable-by-default design is already there.

---

## Honest Limitations

**Alpha API.** Interfaces in the "Evolving" table above may change between minor
versions. If you adopt Chirp today, pin your version.

**Python 3.14+ only.** Chirp does not and will not support older Python. This is
a strategic bet on free-threading, not a constraint to lift later.

**Small ecosystem.** The Bengal stack is young. chirp-ui, Kida, and Pounce are
purpose-built companions. Third-party plugins do not yet exist. Teams must own
more of the stack than they would with Flask or Django.

**No ORM.** Chirp ships typed async database access helpers but deliberately
excludes an ORM. PostgreSQL and SQLite adapters are wired in; everything else is
the application's responsibility.

**No admin panel.** Django's admin is a productivity multiplier for data-heavy
apps. Chirp does not have an equivalent. Build it with Chirp's own tools or use
Django for that class of application.

---

## Summary

| Dimension | Assessment |
|-----------|------------|
| **Stability** | Alpha. Core routing/negotiation/SSE stable; composition APIs settling. |
| **Test quality** | High. ~1:1 test-to-source ratio; 80% branch coverage enforced. |
| **Type safety** | High. Zero `type: ignore` target; PEP 561 typed; strict `ty` config. |
| **Free-threading** | Native. Structural, not patched. Ready for Python 3.14t today. |
| **Value proposition** | Strong for HTMX-driven, HTML-over-the-wire Python apps. |
| **Production readiness** | Possible with version pinning; Pounce server is production-grade. |
| **Ecosystem depth** | Thin but growing; third-party plugins do not yet exist. |
| **Recommended for** | Teams building htmx apps, real-time dashboards, streaming UIs on Python 3.14+. |

---

## Next Steps

- [[docs/about/comparison|When to Use Chirp]] — How Chirp fits against Flask, FastAPI, and Django
- [[docs/about/architecture|Architecture]] — How the three-layer design enforces these properties
- [[docs/about/thread-safety|Thread Safety]] — Free-threading patterns in detail
- [[docs/get-started/quickstart|Quickstart]] — Try it yourself

# Chirp 0.1.2

**Release date:** 2026-02-18

## Highlights

This release adds **Islands (V1)** for framework-agnostic high-state UI widgets, **chirp-ui integration**, **auth hardening** for production, and **Alpine.js support**.

### Islands (V1)

Framework-agnostic contract for isolated high-state UI widgets (editors, canvases, complex grids):

- Mount metadata: `data-island`, `data-island-props`, `data-island-src`, `data-island-version`, `data-island-primitive`
- `app.check()` validates island mounts and primitive contracts
- No-build primitive style: plain ES modules from `/static/islands/*.js` without a bundler
- Runtime diagnostics and safety checks

See the [Islands guide](https://lbliii.github.io/chirp/docs/guides/islands/) for details.

### chirp-ui Integration

- `chirp.ext.chirp_ui.use_chirp_ui(app)` registers chirp-ui static files (CSS, themes)
- Template loader auto-detects chirp-ui when installed
- Optional `ui` extra: `pip install bengal-chirp[ui]`

### Auth Hardening

Production-ready authentication and abuse protection:

- **AuthRateLimitMiddleware** — Rate limit login/reset endpoints
- **LoginLockout** — Lockout and backoff for repeated failures
- **SecurityAudit** — Audit events for failures, lockouts, and blocked attempts

See the [Auth hardening guide](https://lbliii.github.io/chirp/docs/guides/auth-hardening/) for the full checklist.

### Alpine.js Support

- `chirp/alpine.html` macros for `x-data`, `x-init`, reactive bindings
- Server-side Alpine integration and `app.check()` validation for Alpine islands
- [Alpine + htmx tutorial](https://lbliii.github.io/chirp/docs/tutorials/alpine-htmx/)

### Other Additions

- **LLM playground example** — Streaming LLM chat with htmx
- **Documentation** — Guides for islands, auth hardening, Alpine + htmx, and no-build high-state

## Changes

- **Dependencies:** `kida-templates>=0.2.2` (was 0.2.1)
- **CI:** Ruff linting, prek pre-commit, GitHub Actions workflow
- **RAG demo:** Updated with chirp-ui integration

## Installation

```bash
pip install bengal-chirp==0.1.2
# or
uv add bengal-chirp==0.1.2
```

With chirp-ui:

```bash
pip install bengal-chirp[ui]
```

## Full Changelog

https://github.com/lbliii/chirp/blob/main/CHANGELOG.md#012--2026-02-18

# Public API

Chirp's blessed import path is `from chirp import ...`. The top-level surface is intentionally
small enough to learn, but wide enough for real apps and extensions.

This page classifies exported names by stability:

- **Stable**: intended for application code. Breaking changes need a changelog fragment and a
  migration note.
- **Provisional**: supported, but still settling. Plugin authors and advanced apps can use these,
  but minor releases may adjust details when the contract improves.
- **Debug / advanced**: exported for diagnostics, tests, and framework-level tooling. Prefer the
  stable return types and app methods for normal app code.
- **Internal**: any module or name not exported from `chirp.__all__`. Importing it is allowed in
  experiments, but it is not a compatibility promise.

For the pre-1.0 audit queue, see `docs/plan-1-0-public-surface-audit.md`.

## Stable Core

These are the everyday imports for Chirp apps:

```python
from chirp import App, AppConfig, Page, Fragment, Template
```

| Area | Names |
|------|-------|
| Application | `App`, `AppConfig` |
| HTTP | `Request`, `Response`, `FileResponse`, `JSONResponse`, `Redirect`, `hx_redirect` |
| Return types | `Template`, `InlineTemplate`, `Fragment`, `Page`, `OOB`, `Stream`, `Suspense`, `TemplateStream`, `EventStream`, `SSEEvent`, `ValidationError`, `FormAction`, `MutationResult`, `Action` |
| Middleware | `Middleware`, `Next`, `AnyResponse` |
| Request context | `g`, `get_request` |
| Errors | `ChirpError`, `ConfigurationError`, `HTTPError`, `MethodNotAllowed`, `NotFound`, `PayloadTooLarge` |
| Forms | `form_from`, `form_or_errors`, `form_values`, `FormBindingError` |
| Auth and security | `get_user`, `current_user`, `login`, `logout`, `login_required`, `requires`, `is_safe_url` |
| Auth and session wiring | `SessionMiddleware`, `SessionConfig`, `get_session`, `regenerate_session`, `AuthMiddleware`, `AuthConfig` |
| Markdown | `MarkdownRenderer` |

### Request notes

`Request.trusted_client_ip` is the blessed accessor for the trusted-proxy-corrected
client IP — use it for rate-limit and audit keying. It returns `client[0]` (falling
back to `"unknown"` when the scope has no client) and **never raises**. It is
fail-closed: it deliberately does not read a raw, client-spoofable `X-Forwarded-For`
header. In production Chirp's ASGI server (pounce) applies the trusted-proxy model
(`AppConfig.trusted_proxies` + `AppConfig.forwarded_for_trusted_hops`) into
`scope["client"]` before the `Request` is built, so `client[0]` is already the
trusted-derived IP; under a non-pounce server that leaves `scope["client"]` as the
raw peer, this is only as trustworthy as that server.

## Provisional Extension Surface

These names are public because extension authors and serious apps need them, but their exact
shape may still evolve before 1.0:

| Area | Names |
|------|-------|
| Contracts | `CheckResult`, `ContractCheck`, `ContractCheckSnapshot`, `ContractIssue`, `Severity`, `ChirpPlugin`, `CHIRP_CAPABILITIES` |
| Suspense internals exposed for templates/checks | `CHIRP_DEFER_PENDING_KEY`, `DEFERRED` |
| HTTP/request helpers | `RequestUrlScope` |
| HTMX details | `HtmxDetails`, `STOP_POLLING` |
| Reactive pages | `ReactiveBus`, `ChangeEvent`, `DependencyIndex`, `BlockRef`, `reactive_stream` |
| Signals (server reactive values) | App methods `app.signal` / `app.derived` / `app.emit`; template globals `signal()` / `signal_block()` / `signal_attrs()` / `signal_connect()`; the auto-registered `/_chirp/live` merge stream; the `app.check()` signal_dead_binding (ERROR) / signal_orphan (INFO) categories |
| Shell actions | `ShellAction`, `ShellActions`, `ShellActionZone`, `ShellMenuItem`, `ShellSubmitSurface` |
| Tools | `ToolCallEvent`, `ToolDef`, `ToolEventBus`, `ToolRegistry` |
| Cache | `DeferredCache`, `get_cache`, `cache_view` |
| Health probes | `HealthCheck` (register via `app.add_health_check`; auto-mounted `/health` + `/ready`) |
| Secure-by-default stack | `secure_stack` |
| Optional UI bridge | `use_chirp_ui` |

## 1.0 Audit Decisions

The 2026-05-03 public-surface audit made one stability correction:
`JSONResponse` is stable. It is an HTTP primitive for narrow progressive-enhancement data islands,
not a parallel REST serialization layer.

Everything else in the provisional table stays provisional for 1.0 unless a focused follow-up
hardens and documents that surface:

| Area | 1.0 Decision | Reason |
|------|--------------|--------|
| Contracts and plugin protocol | Keep provisional | Contract category shape, severity defaults, and extension hooks are still active design space. |
| Suspense sentinels | Keep provisional | They expose render-pipeline internals for templates and checkers. |
| HTMX details and `STOP_POLLING` | Keep provisional | Header parsing and polling semantics need their own public contract before stabilization. |
| Reactive pages | Keep provisional | The free-threaded event story is tested, but the app-author API and examples are still settling. |
| Signals (server reactive values) | Keep provisional | The single-node `signal()`/`@app.derived` surface ships, but the multi-worker `SignalBus` backplane + the pure-derived contract are still in design (see `plan/drafted/rfc-live-sse-topics.md` §12). |
| Shell actions | Keep provisional | They depend on the ChirpUI app-shell contract and should stabilize with that integration. |
| Tool registry/events | Keep provisional | MCP/tool integration is useful but young compared with the core hypermedia surface. |
| Cache helpers | Keep provisional | Backend behavior and cache-key semantics need a public contract before stabilization. |
| `use_chirp_ui` bridge | Keep provisional | It couples this package to `chirp-ui` runtime and manifest behavior. |

## `chirp.security` Module Surface

A few public helpers live on the `chirp.security` module rather than the top-level
`from chirp import` surface. They are **not** part of the `chirp.__all__` snapshot
(so this listing is maintained by hand), but they are documented-public and stable
for application code.

```python
from chirp.security import (
    hash_password,
    verify_password,
    verify_login,
    verify_and_upgrade,
    needs_rehash,
    resolve_permissions,
)
```

| Name | Signature | Purpose |
|------|-----------|---------|
| `hash_password` | `(password: str) -> str` | Hash a password with argon2id (`chirp[auth]`) or stdlib scrypt fallback; returns a PHC string. |
| `verify_password` | `(password: str, phc_hash: str) -> bool` | Verify against a stored hash; auto-detects the algorithm from the PHC prefix. |
| `verify_login` | `(password: str, phc_hash: str \| None) -> bool` | Login verification that resists user-enumeration timing: an unknown user (`phc_hash is None`) still runs a decoy verify. Pass `None` for "no such user". |
| `verify_and_upgrade` | `(password: str, phc_hash: str) -> tuple[bool, str \| None]` | Verify and opportunistically return a fresh hash when the password is correct **and** the stored hash is below current cost. `(True, new_hash)` / `(True, None)` / `(False, None)`. Never rehashes a wrong guess. |
| `needs_rehash` | `(phc_hash: str, *, upgrade_algorithm: bool = False) -> bool` | Report whether a stored hash is below current cost parameters. The algorithm-upgrade clause (scrypt stale because argon2 is now installed) is gated behind `upgrade_algorithm`, off by default. |
| `resolve_permissions` | `(group_blobs: Iterable[Mapping[str, Any] \| Iterable[str]], *, base: frozenset[str] = frozenset()) -> frozenset[str]` | OR-merge (most-permissive-wins union) a user's group permission blobs into the flat `frozenset` the gate checks. Accepts both flat `Iterable[str]` blobs and nested truthy-leaf `Mapping` blobs (flattened to dotted keys, only truthy leaves). Call it in your own `load_user`; matching stays exact (no dotted-prefix coverage). |

The route-protection helpers (`login_required`, `requires`) and lockout/audit
helpers (`LoginLockout`, `LockoutConfig`, `set_security_event_sink`) are also
exported from `chirp.security`.

## Debug And Advanced

These are exported so debugging, tests, and framework tooling can inspect how Chirp resolved a
request. They are not the first tool for application code:

| Area | Names |
|------|-------|
| Render planning | `RenderPlan`, `get_render_plan`, `ViewRef`, `RegionUpdate` |
| Composition | `PageComposition` |
| Navigation swaps | `SwapResolution`, `resolve_navigation_swap` |

## Change Rules

- Adding a top-level name requires updating `chirp.__all__`, the lazy import registry, the
  stability classification, tests, and this page.
- Removing or renaming a stable name requires a deprecation period and migration note.
- Provisional names can change faster, but changes still need a changelog fragment.
- New return types, `AppConfig` fields, mandatory dependencies, and render-pipeline API changes
  need design review before implementation.

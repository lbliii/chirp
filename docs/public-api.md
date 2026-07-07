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
| Return types | `Template`, `InlineTemplate`, `Fragment`, `Page`, `OOB`, `Stream`, `Suspense`, `TemplateStream`, `EventStream`, `SSEEvent`, `ValidationError`, `FormAction`, `MutationResult`, `SignalEmit`, `Action` |
| Middleware | `Middleware`, `Next`, `AnyResponse` (register with `app.add_middleware(mw, *, priority=0)`) |
| Request context | `g`, `get_request` |
| Errors | `ChirpError`, `ConfigurationError`, `HTTPError`, `MethodNotAllowed`, `NotFound`, `PayloadTooLarge` |
| AI (`pip install chirp[ai]`) | `LLM`, `AIError`, `ProviderError`, `ProviderNotInstalledError`, `StructuredOutputError` |
| Tools | `ToolCallEvent`, `ToolDef`, `ToolEventBus`, `ToolRegistry` |
| Forms | `form_from`, `form_or_errors`, `form_values`, `FormBindingError` |
| Auth and security | `get_user`, `current_user`, `login`, `logout`, `login_required`, `requires`, `is_safe_url` |
| Auth and session wiring | `SessionMiddleware`, `SessionConfig`, `SessionSignalMiddleware`, `SessionSignalConfig`, `get_session`, `regenerate_session`, `AuthMiddleware`, `AuthConfig` |
| Markdown | `MarkdownRenderer` |

### Request notes

The experimental RFC 10008 route keyword is an additive API, but it tightens
previously generic method-token behavior: an existing route registered with
`methods=["QUERY"]` must now add a non-empty `query_media_types=(...)`
declaration or freeze fails with migration guidance. Routes for every other
method are unchanged. QUERY remains provisional and ASGI-only while the
remaining RFC 009 promotion gates are open.

`Request.trusted_client_ip` is the blessed accessor for the trusted-proxy-corrected
client IP — use it for rate-limit and audit keying. It returns `client[0]` (falling
back to `"unknown"` when the scope has no client) and **never raises**. It is
fail-closed: it deliberately does not read a raw, client-spoofable `X-Forwarded-For`
header. In production Chirp's ASGI server (pounce) applies the trusted-proxy model
(`AppConfig.trusted_proxies` + `AppConfig.forwarded_for_trusted_hops`) into
`scope["client"]` before the `Request` is built, so `client[0]` is already the
trusted-derived IP; under a non-pounce server that leaves `scope["client"]` as the
raw peer, this is only as trustworthy as that server.

`Request` exposes an <code>htmx</code> namespace that normalizes both supported
htmx request-header generations. <code>target</code> / <code>source</code>
preserve raw metadata; <code>target_id</code>, <code>target_tag</code>,
<code>source_id</code>, and <code>source_tag</code> expose parsed element
identity; <code>request_type</code> is the validated htmx 4
<code>"full"</code> / <code>"partial"</code> value. The flat
<code>htmx_target_*</code>, <code>htmx_source_*</code>, and
<code>htmx_request_type</code> properties delegate to that namespace.
<code>htmx_trigger</code> returns the htmx 2 <code>HX-Trigger</code> id or falls
back to the htmx 4 <code>HX-Source</code> id. <code>htmx_trigger_name</code>
remains a legacy-only value because htmx 4 does not transmit an element
<code>name</code>.

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
| Signals (server reactive values) | App methods `app.signal` / `app.derived` / `app.emit`; template globals signal()/signal_block()/signal_bind() (signal_attrs alias)/signal_connect(); the auto-registered `/_chirp/live` merge stream; the `app.check()` signal_dead_binding (ERROR) / signal_orphan (INFO) / signal_connect_budget (INFO) categories |
| Dynamic template reachability | App method `app.declare_template(template, *, blocks=())`; surrounding name whitespace is normalized, template_declaration errors validate names, and the dead-template check treats only declared templates as reachable |
| Experimental HTTP QUERY | App method `app.route(..., methods=["QUERY"], query_media_types=(...))`; declarations freeze as normalized immutable media ranges and the ASGI path enforces Content-Type, body limits, and response Accept negotiation |
| Shell actions | `ShellAction`, `ShellActions`, `ShellActionZone`, `ShellMenuItem`, `ShellSubmitSurface` |
| Cache | `DeferredCache`, `get_cache`, `cache_view` |
| Health probes | `HealthCheck` (register via `app.add_health_check`; auto-mounted `/health` + `/ready`) |
| Secure-by-default stack | `secure_stack` (optional `auth=AuthConfig(...)` and `audit=AuditConfig(...)` legs) |
| Optional UI bridge | `use_chirp_ui` |
| Experimental browser-agent forms | `WebMCPForm`; opt in through `FormContract.webmcp`, then render the frozen `webmcp_form_attrs()` and `webmcp_control_attrs()` template globals |

`WebMCPForm` implements only the declarative form vocabulary pinned to WebMCP
proposal commit `0b676d27a08aafd3b4f8a709756eeeab342fd9bd`. It is provisional,
adds no imperative JavaScript registry, and never changes the ordinary form
submission path. Mutation forms cannot enable the toolautosubmit attribute.
The `webmcp` startup contract category validates the projection and its native
fallback as ERROR-only safety diagnostics. `chirp check --json --coverage` and
contract diffs include declared/compiled projection and parameter counters.

## 1.0 Audit Decisions

The 2026-05-03 public-surface audit made one stability correction:
`JSONResponse` is stable. It is an HTTP primitive for narrow progressive-enhancement data islands,
not a parallel REST serialization layer.

Phase 1 AI work (#421/#430, 2026-06-22) promoted the LLM client, AI error types, and tool
registry/event bus to stable after unit tests, OTel spans, and SSE trace-context fixes landed.

Everything else in the provisional table stays provisional for 1.0 unless a focused follow-up
hardens and documents that surface:

| Area | 1.0 Decision | Reason |
|------|--------------|--------|
| Contracts and plugin protocol | Keep provisional | Contract category shape, severity defaults, and extension hooks are still active design space. |
| Suspense sentinels | Keep provisional | They expose render-pipeline internals for templates and checkers. |
| HTMX details and `STOP_POLLING` | Keep provisional | Header parsing and polling semantics need their own public contract before stabilization. |
| Reactive pages | Keep provisional | The free-threaded event story is tested, but the app-author API and examples are still settling. |
| Dynamic template reachability | Keep provisional | The setup declaration is validated and immutable, but registry patterns may broaden before 1.0. |
| Experimental HTTP QUERY | Keep provisional | RFC 10008 request enforcement ships only for explicit routes on the ASGI path; discovery, client ergonomics, caching, filesystem pages, and production promotion remain separately gated. |
| Signals (server reactive values) | Keep provisional | The single-node `signal()`/`@app.derived` surface ships, but the multi-worker `SignalBus` backplane + the pure-derived contract are still in design (see `plan/drafted/rfc-live-sse-topics.md` §12). |
| Shell actions | Keep provisional | They depend on the ChirpUI app-shell contract and should stabilize with that integration. |
| Tool registry/events | **Stabilized (2026-06-22)** | Phase 1 (#421/#430): MCP server surface, event bus, OTel spans, and integration tests meet the stable bar. |
| LLM + AI errors | **Stabilized (2026-06-22)** | Phase 1 (#421/#430): top-level lazy imports, unit tests, OTel spans; `stream_to_fragments` / `stream_with_sources` remain `chirp.ai` helpers until a follow-up. |
| Phase 2 AI loop (`AgentRun`, `stream_events`, `ConversationStore`, MCP client) | **Provisional (2026-06-22)** | Shipped in #431–#437; documented under `chirp.ai` / `chirp.tools.client`; promote after example refactors and soak time. |
| Cache helpers | Keep provisional | Backend behavior and cache-key semantics need a public contract before stabilization. |
| `use_chirp_ui` bridge | Keep provisional | It couples this package to `chirp-ui` runtime and manifest behavior. |

## `chirp.testing` Module Surface

Testing helpers are imported from `chirp.testing`, not from the top-level
`chirp` namespace. `TransitionObservation`, `TransitionCoverage`,
`transition_observation`, and `transition_coverage` are provisional debug/test
evidence helpers. They consume real debug responses, correlate them with opaque
compiled transition IDs, and report only caller-declared coverage expectations;
they do not replace browser behavior tests.

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

## `chirp.middleware` Module Surface

Built-in middleware and their config dataclasses live on the `chirp.middleware`
module rather than the top-level `from chirp import` surface. They are **not**
part of the `chirp.__all__` snapshot (this listing is maintained by hand) but are
documented-public and stable for application code.

```python
from chirp.middleware import (
    AuthRateLimitMiddleware,
    AuthRateLimitConfig,
    RateLimitBackend,
    redis_rate_limit_backend,
)
```

| Name | Purpose |
|------|---------|
| `AuthRateLimitMiddleware` | Keyed rate limiter. Defaults limit the common auth endpoints by `request.trusted_client_ip`; with `key_fn` + open path targeting it limits any route/group (per-user, per-resource, per-tenant). |
| `AuthRateLimitConfig` | Config: `requests`, `window_seconds`, `block_seconds`, `methods`, `paths` (`()` = all routes), `key_header`, `key_fn` (`(Request) -> str \| None`; `None` skips the request), `error_template` / `error_block` (HTML 429 for htmx POSTs), `backend`. |
| `RateLimitBackend` | Protocol for pluggable rate-limit storage (`check_and_update(...)`). Implement it for a custom shared backend. |
| `redis_rate_limit_backend` | `(redis_url, key_prefix="chirp:ratelimit:") -> RateLimitBackend` — Redis sliding-window backend shared across workers (requires `chirp[redis]`). |
| `AuditMiddleware` | Opt-in per-request who/what/when/status audit trail. Emits one `http.request` event per audited request through the existing `emit_security_event` sink (`status_code`/`source_ip`/`user_agent`/`user_id` in `details`). OFF by default; downgrades to metadata-only and never drains the body for `StreamingResponse`/`SSEResponse`/`FileResponse` (`Stream`/`Suspense`/`EventStream`). Source IP from `request.trusted_client_ip` (never a re-parsed `X-Forwarded-For`). |
| `AuditConfig` | Config: `level` (`"none"` default OFF, `"metadata"`, `"request"`, `"request_response"`), `max_body_bytes` (default `4096`), `audited_methods` (default `MUTATING_METHODS`), `redact_keys` (default `("password", "token", "secret", "csrf_token")`, case-insensitive form-key masking), `redact_patterns` (regex masking). Frozen + slotted. |

(The other built-in middleware — `SessionMiddleware`, `CSRFMiddleware`,
`SecurityHeadersMiddleware`, `AuthMiddleware`, `CORSMiddleware`,
`AllowedHostsMiddleware`, `StaticFiles`, `CSPNonceMiddleware`, `HTMLInject` — are
also `chirp.middleware` exports.)

## Middleware Ordering

`app.add_middleware(middleware, *, priority=0)` registers a middleware in the
request pipeline. The optional keyword-only `priority` makes the resolved order
explicit and independent of registration order: at freeze the user middleware is
stably sorted by `(priority, registration_order)`, and **lower priority runs
outermost** (it wraps the higher-priority middleware). The default `priority=0`
keeps registration order, so existing apps are byte-identical. Built-in
middleware stays positionally pinned around the user chain. A `priority` that
places CSRF middleware outside session middleware still raises a configuration
error at freeze, and `app.check()` reports the resolved chain under the INFO
`middleware_chain` diagnostic category (see the contract categories reference).

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

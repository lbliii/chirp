---
title: Contract Category Reference
description: app.check categories, default severity, fix targets, and severity override examples
draft: false
weight: 35
lang: en
type: doc
tags: [contracts, app-check, diagnostics, reference]
keywords: [contract categories, app.check, chirp check, severity, warnings-as-errors]
category: reference
---

`app.check()` validates your hypermedia wiring at startup and reports every
problem as a `(category, severity, message)` triple. The **category** is the
stable handle you target in CI policy; the **message** names the exact route,
template, block, selector, registration, config field, middleware, or import
string to fix. This page lists every category, its default severity, and what to
change.

New here? Start with [[docs/quality/contracts-debugging/debugging-swaps|how to read and diagnose check output]] and [[docs/about/core-concepts/app-lifecycle|how app.check runs at startup]].

## The two policy levers

`chirp check myapp:app --warnings-as-errors` promotes warnings at the CLI
boundary. For app-specific policy, override a category before running checks:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("dead", Severity.WARNING)
app.override_contract_severity("page_handlers", Severity.WARNING)
```

:::{warning}
Overrides are deliberately category-scoped. **Do not demote fail-loud
categories** such as missing required OOB regions (`oob_registry`) or broken SSE
listeners (`sse`, `signal_dead_binding`) unless you have a temporary migration
plan and a narrower test that covers the user-visible path. Demoting these turns
a startup error into silently-broken DOM updates in production.
:::

:::{note} Severities are defaults, and several are env-aware
Rows that read `ERROR / WARNING` or `ERROR / WARNING / INFO` pick their severity
from `config.env`: most security and deploy categories are silent in
development, `WARNING` in staging, and `ERROR` in production. To see how a dev
app would fare in production without changing your config, use `chirp check
--deploy` (covered in the production-posture preflight section below).
:::

## Routing And Pages

| Category | Default severity | Fix target |
|---|---|---|
| `routing` | ERROR | Replace Flask-style route params such as `<id>` with Chirp's `{id}` route syntax. |
| `route_names` | ERROR | Rename one route or set an explicit module-level route name so `app.url_for()` is unambiguous. |
| `route_contract` | ERROR / INFO / WARNING | Align filesystem route files, metadata, and declared contracts with discovered routes. See [[docs/quality/contracts-debugging/route-contract|the route-directory contract]]. |
| `page_handlers` | ERROR / WARNING | Add a recognized `page.py` handler (`get`, `post`, another HTTP method, or `handler`) and fix handler-shaped typos. |
| `method` | ERROR | Ensure handlers are callable and route methods are supported. |
| `target` | ERROR | Fix route target declarations that point at missing routes. |
| `page_context` | WARNING | Move page block dependencies into the context available to direct fragment renders. |
| `page_shell` | ERROR | Register or correct app-shell targets, outlets, and shell contracts used by filesystem pages. |
| `layout_chain` | INFO / WARNING | Fix duplicate layout targets, default inner `body` targets, broad `hx-disinherit`, or inheritance inside composed layouts. |
| `layout_outlet` | WARNING | Declare and register the outlet used by boosted navigation so narrow htmx responses are selected correctly. |
| `layout_frame` | WARNING | Keep immutable frame targets out of the fragment-target registry. |
| `context_cascade` | INFO / WARNING | Fix `_context.py` signatures, inherited context providers, and intentional child overrides. |
| `mount_app_merge` | INFO | Review parent-wins dropped entries from `mount_app()` such as globals, filters, providers, handlers, and severity overrides. |
| `setup` | ERROR | Fix checker setup problems such as missing template loaders before trusting downstream contract output. |

## Templates And Blocks

| Category | Default severity | Fix target |
|---|---|---|
| `dead` | WARNING | Remove unused templates or add a route, include, import, layout, or explicit docs/tool reference. |
| `orphan` | INFO | Reference the route from a template, mark it explicitly referenced, or accept that static analysis cannot see dynamic navigation. |
| `fragment` | ERROR | Fix `FragmentContract` declarations that point at missing templates or blocks. |
| `fragment_scope` | WARNING | Move imports or bindings into the fragment block when direct block rendering would skip ancestor scope. |
| `fragment_target_orphan` | ERROR / WARNING | Register the missing block for a required fragment target, or mark legitimately absent regions optional. |
| `fragment_target_scan` | ERROR | Fix the template parse/load error that prevented fragment target orphan checks from completing. |
| `unreachable_block` | WARNING | Move sibling page blocks under the rendered page root or make them real fragment targets. |
| `composition_extends` | WARNING | Stop extending layout templates from page templates; compose pages into layout content blocks instead. |
| `htmx_partial` | ERROR | Correct `<htmx-partial>` sources, blocks, and route references. |
| `inline_template` | WARNING | Replace inline template strings when a named template would be checkable and reusable. |
| `boundary` | INFO | Keep route, template, and extension boundaries aligned so checks can map diagnostics to the right source. |
| `islands` | ERROR / WARNING | Register island roots and targets consistently when island strictness is enabled. |
| `component` | ERROR | Fix Kida/chirp-ui component-call diagnostics; precision depends on available typed component metadata. |
| `template_contract` | WARNING | Replace legacy component action contracts with current declarations. |
| `template_context` | ERROR / WARNING | Add missing dotted context paths to the provided or optional contract data, or stop reading them. |
| `template_escape` | WARNING | Review trusted-markup or escaping diagnostics surfaced by Kida. |
| `template_privacy` | WARNING | Remove private literals or mark non-public template content appropriately. |
| `i18n_missing_key` | WARNING | Add the `t("…")` key to the locale JSON catalog(s) under the i18n directory, or remove the `t()` call. |
| `macro_css` | WARNING | Activate chirp-ui (`use_chirp_ui(app)`) or ship your own CSS for the core-macro classes (`chirp-dropdown`, `chirp-modal`, `field--error`, …) when neither is present. |

## HTMX And Swaps

| Category | Default severity | Fix target |
|---|---|---|
| `hx-target` | WARNING | Fix static `hx-target="#id"` selectors that do not match any known template ID. |
| `hx-indicator` | WARNING | Fix static `hx-indicator="#id"` selectors that do not match any known template ID. |
| `hx-boost` | WARNING | Use only `hx-boost="true"` or `hx-boost="false"` for static boost values. |
| `selector_syntax` | ERROR | Fix invalid selector syntax in static htmx selector-bearing attributes. |
| `select_inheritance` | WARNING | Override inherited broad `hx-select` with an explicit selector or `hx-select="unset"` on the mutating element. `hx-disinherit` only affects descendants, not the element itself. |
| `swap_safety` | INFO / WARNING | Add explicit local targets or isolate SSE swaps from broad inherited `hx-target`/`hx-swap`. |
| `fragment_island` | INFO | Add `hx-disinherit` or a fragment-island wrapper around local mutation targets. |
| `view_transition_scope` | WARNING | Scope View Transitions to navigation-only elements, not broad OOB/SSE live-update containers. |
| `oob_registry` | ERROR / WARNING | Add the registered OOB block/target, fix a typo, or make the region optional only when absence is legitimate. See [[docs/quality/contracts-debugging/oob-registry|the OOB registry]]. |
| `oob_target` | WARNING | Fix `hx-swap-oob` IDs that do not appear in any known template. |
| `duplicate_id` | WARNING | Remove or rename repeated static `id="..."` values in the same template — duplicate ids break targeting and accessibility. |
| `oob_fragment_orphan` | WARNING | Wire a route, EventStream, or signal render callback that yields the OOB fragment block, or remove the dead swap target. |
| `htmx_provisioned` | WARNING | Provision htmx with `AppConfig(htmx=True)` or an htmx `<script>` in the layout chain when a template emits `hx-*`/`sse-*` attributes. |

## SSE And Reactive

| Category | Default severity | Fix target |
|---|---|---|
| `sse` | ERROR | Fix route-level `SSEContract` declarations that point at missing or inconsistent event/template data. |
| `sse_self_swap` | ERROR | Move `sse-swap` from the `sse-connect` element to a child sink. |
| `sse_scope` | ERROR | Add an SSE scope boundary such as `hx-disinherit="hx-target hx-swap"` when streams live inside broad htmx targets. |
| `sse_crossref` | ERROR / INFO | Align `sse-swap="event"` listeners with declared or inferred `SSEEvent(event=...)` and `Fragment(target=...)` channels. |
| `sse_speculation` | WARNING | Add `referenced=True` to SSE routes so browser speculation does not open long-lived prefetch streams. |
| `sse_auth_gate` | ERROR / WARNING | Register `AuthMiddleware` (after `SessionMiddleware`) when an `EventStream` generator reads the request user (`get_user()` / `current_user()`). Without it the connect-time-captured SSE user is `AnonymousUser` for the whole stream. Env-aware (silent dev / WARNING staging / ERROR prod). See the dropdown below. |
| `sse_context` | WARNING | Semantic nudge only — the pattern WORKS. SSE user identity is **pinned at connect time**; a mid-stream logout / permission change is not reflected. Re-check authorization per event (or close the stream on revoke) for an auth-sensitive long-lived feed. Never ERROR. See the dropdown below. |
| `reactive_block` | ERROR | Fix `DependencyIndex` `BlockRef` template or block names. |
| `reactive_cycle` | WARNING | Remove cycles from `DependencyIndex.derive()` relationships. |
| `reactive_paths` | WARNING | Register every declared emitted path in the dependency index or remove stale metadata. |
| `reactive_audience` | WARNING | Pair audience-filtered scopes with `reactive_stream(..., connection=ConnectionInfo(...))`. |
| `live_block_unknown` | ERROR | Fix `live_block` references to unknown templates or blocks. |
| `live_block_unreachable_route` | ERROR | Reference live blocks from reachable routes or remove stale declarations. |
| `signal_dead_binding` | ERROR | Declare a `@app.signal('x')` / `@app.derived('x', ...)` producer for every `signal('x')` / `signal_block('x')` / `sse-swap="x"` binding under the merged `/_chirp/live` connection, or fix the name. A bound signal with no registered producer never updates. |
| `signal_raw_sse_swap` | INFO | Prefer `{{ signal_attrs('x') }}` over hand-written `sse-swap="x"` on pages composed under `signal_connect()` so the binding is validated. |
| `signal_orphan` | INFO | Bind the registered signal with `signal()`/`signal_block()` in a template, or remove the unused producer. An orphan signal is produced but never displayed. |
| `signal_scope` | ERROR / WARNING | Register `SessionMiddleware` before using `audience="session"` signals so each connection can resolve its `/_chirp/live?aud=…` key. WARNs when a derived signal depends on both global and session-scoped deps — verify the mixed dependency graph is intentional. |

## Forms, Commands, And Safety

| Category | Default severity | Fix target |
|---|---|---|
| `form` | ERROR / WARNING | Align `FormContract` fields with actual `<input>`, `<select>`, and `<textarea>` names. |
| `form_contract` | INFO | Add a `FormContract` to POST routes targeted by static forms, or accept the informational gap. |
| `csrf_form` | WARNING | Add `{{ csrf_field() }}`, `csrf_token()`, or `_csrf_token` to static mutating forms when `CSRFMiddleware` is active. |
| `command` | WARNING | Fix command declarations, route handlers, or command metadata. |
| `commandfor` | WARNING | Fix command target references that cannot be resolved. |
| `vary` | WARNING | Add required `Vary` behavior for cache-sensitive htmx or middleware paths. |
| `allowed_hosts` | ERROR / WARNING | Configure explicit hosts outside development instead of `allowed_hosts=("*",)`. |
| `trusted_proxies` | WARNING | Configure explicit reverse-proxy peer IPs/hostnames instead of `trusted_proxies=("*",)` outside development. Details in the dropdown below. |
| `csrf_session` | ERROR | Register `SessionMiddleware` before `CSRFMiddleware`. |
| `security_stack` | ERROR / WARNING | Wire the secure-by-default stack on apps with mutating routes. See the `security_stack` canonical reference below. |
| `auth_middleware` | ERROR / WARNING / INFO | Register `AuthMiddleware` (after `SessionMiddleware`) when any route declares auth via `RouteMeta.auth` or `@login_required`/`@requires`. Without it the auth gate's `get_user()` raises `LookupError` → 500. See the dropdown below. |
| `auth_spec` | ERROR / WARNING | Fix a `RouteMeta.auth` permission/policy that will silently fail. Registry-backed when you declare `app.register_permission()` / `app.register_policy()` (unknown permission/policy → ERROR); otherwise a high-signal reserved-token typo heuristic. See the dropdown below. |
| `cookie_secure` | ERROR / WARNING | Make the session cookie `Secure`. Keep `SessionConfig(secure="auto")` (resolves to `Secure` in production/staging) or set `secure=True`. A `samesite="none"` cookie that is not `Secure` is an env-independent ERROR. See the dropdown below. |
| `hsts` | WARNING | Set `AppConfig(strict_transport_security="max-age=63072000; includeSubDomains")` on a production app with an auth/mutating surface — once you have confirmed it is only ever reached over HTTPS. Never auto-emitted. See the dropdown below. |
| `password_extra` | WARNING | Install `chirp[auth]` (argon2id) on a production app with a login/mutating surface — without it password hashing falls back to stdlib scrypt. Advisory only (silent in development); existing scrypt hashes upgrade on next login. See the dropdown below. |
| `csp_nonce` | ERROR / WARNING | Enable a per-request nonce mechanism (`AppConfig(csp_nonce_enabled=True)`) so framework inline scripts carry a nonce under an inline-forbidding CSP. See the dropdown below. |
| `chirpui_csp` | ERROR / WARNING | **chirp-ui apps only.** Remove a conflicting static CSP so `use_chirp_ui`'s auto-wired nonce CSP can keep Alpine alive. See the dropdown below. |
| `middleware_signature` | ERROR / WARNING | Make middleware callable as `async __call__(request, next)`. |
| `static_streaming` | WARNING | Keep `StaticFiles` `static_stream_threshold` sane so large static files stream from disk instead of buffering into memory. Warns when the threshold is `<= 0` or effectively unbounded (`>= 1 GiB`). |
| `secret_key` | ERROR / WARNING | Set a production `secret_key` and use an adequately long value. |
| `nojs_floor` | INFO | Return `FormAction` (303 for plain POST, fragments for htmx) from mutating routes instead of an htmx-only `Fragment`/`OOB`. INFO by default; promote with `override_contract_severity("nojs_floor", Severity.ERROR)` to enforce the no-JS floor. |
| `deploy_debug` | ERROR | Set `debug=False` (or `CHIRP_DEBUG=0`) when `env="production"`. |
| `deploy_metrics` | ERROR | Change `metrics_path` or move the colliding application route so the Prometheus endpoint does not shadow a route. |
| `deploy_health` | ERROR | Rename the colliding application route or change `health_path` / `ready_path` so the auto-mounted `/health` + `/ready` probes are not shadowed by an app route. |
| `deploy_sentry` | WARNING | Set a non-zero `sentry_traces_sample_rate` when a Sentry DSN is configured, or clear the DSN. |

::::{dropdown} `trusted_proxies` — why `"*"` trusts every peer
`trusted_proxies=("*",)` trusts every direct peer's `X-Forwarded-For` header,
which lets a client spoof its own IP — bypassing rate limits and skewing audit
logs. Always `WARNING`: silent in development, fires in staging and production.
Configure explicit reverse-proxy peer IPs or hostnames instead.
::::

::::{dropdown} `csp_nonce` — how nonce-per-request works
This fires when an inline-forbidding CSP (`script-src` without `'unsafe-inline'`)
lacks a per-request nonce mechanism *while* a framework inline-script feature is
enabled. Every framework inline `<script>` — Alpine `safeData`, `safe_target`,
`sse_lifecycle`, `delegation`, `view_transitions`, `islands`,
`speculation_rules`, and Suspense initial-load scripts — is built per request
from the live nonce, so it is nonced **whenever a nonce mechanism is active**
(`CSPNonceMiddleware` or `csp_nonce_enabled=True`, which auto-wires it).

The genuinely un-nonceable case is a static `SecurityHeadersMiddleware` /
app-level CSP that drops `'unsafe-inline'` *without* a nonce mechanism: then
those scripts emit without a nonce and the browser silently blocks them.
Severity is env-aware (ERROR in production, WARNING in staging, **silent in
development**), mirroring `security_stack`.

**Fix:** enable `CSPNonceMiddleware` / `AppConfig(csp_nonce_enabled=True)` so the
framework scripts carry the live nonce; or, discouraged, add `'unsafe-inline'` to
`script-src`. Stays silent when no inline-forbidding policy is in force, when a
nonce mechanism is active (everything nonceable), or when no inline-script
feature is enabled. `alpine_csp=True` ships no inline bootstrap and is
unaffected.
::::

::::{dropdown} `chirpui_csp` — why chirp-ui needs unsafe-eval / unsafe-inline
A no-op for non-chirp-ui apps. When chirp-ui is active, it flags an effective
CSP that would silently kill Alpine. chirp-ui's shell evaluates Alpine
expressions as JS (needs `script-src 'unsafe-eval'`) and toggles visibility via
inline `style="display:none"` attributes that **cannot be nonced** (needs
`style-src 'unsafe-inline'`).

`use_chirp_ui(app)` flips `csp_nonce_enabled=True`, so the compiler auto-wires
`CSPNonceMiddleware` with both relaxations and a stock chirp-ui app passes with
**no hand-written CSP**. This check fires when an app pins a conflicting static
`SecurityHeadersMiddleware` / app-level CSP that forbids the inline bootstrap /
eval or inline style (a static header overrides the nonce header), or when no
nonce mechanism and no Alpine-compatible CSP are in force. Severity is env-aware
(ERROR in production, WARNING in staging, **silent in development**), mirroring
`csp_nonce` / `security_stack`.

**Fix:** remove the conflicting static CSP and let `use_chirp_ui`'s auto-wired
nonce CSP own the header, or relax `script-src` / `style-src` to match Alpine's
needs. The `style-src 'unsafe-inline'` relaxation is scoped to `style-src` only —
`script-src` stays nonce-only.
::::

### `chirp check --deploy`: production-posture preflight

The env-aware categories above (`secret_key`, `allowed_hosts`, `security_stack`,
`cookie_secure`, `hsts`, `password_extra`, `auth_middleware`, `auth_spec`,
`sse_auth_gate`, `sse_context`, `csp_nonce`,
`chirpui_csp`, `deploy_debug`,
`deploy_metrics`, `deploy_health`, `deploy_sentry`) pick their severity from `config.env`. In development most are silent or WARNING,
so a dev app passes `app.check()` while still carrying production-blocking
misconfigurations. `chirp check myapp:app --deploy` answers "would this pass in
production?" without changing your config: it runs those rules against a
throwaway **production-posture view** of the config and treats warnings as
errors (`--deploy` implies `--warnings-as-errors`). It is tighten-only — only
severities rise, so a genuinely deploy-ready app still passes — and it never
mutates the running app. Programmatically this is `app.check(deploy=True)`. Use
it as a CI deploy gate.

### `security_stack`: canonical reference

`security_stack` is the canonical owner of the **mutating route** definition and
the secure-by-default presence check. Severity is env-aware: missing
`CSRFMiddleware` or `SessionMiddleware` is **ERROR in production, WARNING in
staging, silent in development**; missing `SecurityHeadersMiddleware` is always
**WARNING** (env-independent). Chirp force-injects no security middleware — the
`chirp new` scaffolds (including `--minimal`) wire `SessionMiddleware` →
`CSRFMiddleware` → `SecurityHeadersMiddleware` for you, so generated apps pass
out of the box. `csrf_session` checks the ordering of that stack; `csrf_form`
checks individual template `<form>` tags; `security_stack` is the route-level
presence check.

**Env-severity matrix.** Two distinct severity tracks:

| Missing middleware | development | staging | production |
|---|---|---|---|
| `CSRFMiddleware` or `SessionMiddleware` | silent | WARNING | ERROR |
| `SecurityHeadersMiddleware` | WARNING | WARNING | WARNING |

::::{dropdown} What counts as a mutating route?
A route is mutating when **either** condition holds:

- It accepts any method in `{POST, PUT, PATCH, DELETE}` — explicit handlers
  (`@app.route("/save", methods=["POST"])`, or `PUT`/`PATCH`/`DELETE`) and
  filesystem `page.py` files that define a `post`/`put`/`patch`/`delete` handler.
- It is a filesystem page that ships `_actions.py` form actions. These pages
  mutate state via POST-to-self dispatched on the `_action` form field. The
  `page.py` may declare **only** `get()` — Chirp does *not* auto-register a
  separate POST route variant — so the route is method-`GET` in the router yet is
  unmistakably a mutating surface. The contract treats a page whose discovered
  `actions` is non-empty as mutating, so a GET-only `_actions.py` page is held to
  the same CSRF/Session bar as a POST route. Because `_actions.py` is
  directory-scoped, every page in a directory that ships one is treated as part
  of that mutating surface — a deliberately conservative, fail-loud attribution,
  since the directory genuinely handles form mutations.

Referenced (transport) routes such as a mutating SSE/API endpoint are
**included** — a mutating endpoint still needs CSRF/session protection, unlike
the no-JS floor (`nojs_floor`), which excludes referenced routes. An app with no
mutating routes emits no `security_stack` issue.

`rules_nojs_floor` already reuses this definition (`is_mutating_route` /
`MUTATING_METHODS`); the forms (`csrf_form`) and auth contracts are the intended
future consumers, rather than each re-deriving "what counts as a mutating route."
::::

### `cookie_secure`: Secure session cookies

A `Secure` cookie is only ever sent over HTTPS. A session cookie without `Secure`
— whether it carries the session data (`CookieSessionStore`) or just the session
id (`RedisSessionStore`) — can be sniffed over a plaintext path and replayed to
hijack the session. The check is **store-agnostic**: both stores emit a
`Set-Cookie`, so it fires on the effective `Secure` flag, never on the store type.

It is a no-op when no `SessionMiddleware` is registered — `security_stack` already
owns the presence check. When a `SessionMiddleware` is present, the check reads
its effective `Secure` flag (`SessionMiddleware.secure`, resolved through the same
`resolve_cookie_secure` the runtime uses, so the check and runtime never
disagree). The blessed default `SessionConfig(secure="auto")` resolves to `Secure`
in production/staging, so a default-config app passes.

**Two severity tracks:**

| Condition | development | staging | production |
|---|---|---|---|
| Session cookie not `Secure` (hardening gap) | silent | WARNING | ERROR |
| `samesite="none"` **and** cookie not `Secure` | ERROR | ERROR | ERROR |

The `samesite="none"` + not-`Secure` case is **env-independent ERROR** because
browsers silently **drop** a `SameSite=None` cookie that is not `Secure` — the
session simply breaks in *every* environment, including development. That is a
correctness footgun, not a hardening preference, so it is reported regardless of
`env`.

**Fix:** keep `SessionConfig(secure="auto")` (the default) and serve over HTTPS in
production/staging, or set `SessionConfig(secure=True)` explicitly. For the
`SameSite=None` case, either add `Secure` or use `samesite="lax"`/`"strict"`.
Severity is env-aware (silent dev / WARNING staging / ERROR prod) for the
hardening track and escalates under `chirp check --deploy`.

### `hsts`: HTTP Strict Transport Security nudge

WARNING (never ERROR) when an app declares `env="production"`, has an auth/mutating
surface (same `is_mutating_route` definition `security_stack` owns), and leaves
`strict_transport_security` unset both on `AppConfig` and on any
`SecurityHeadersMiddleware`. Without HSTS a first request over plain HTTP can be
downgraded/MITM'd before the redirect to HTTPS.

This is deliberately a **WARNING + docs nudge only** — Chirp does **not**
auto-emit an HSTS header, and `strict_transport_security=None` is **not**
overloaded to mean "auto"; `None` stays "off". An HSTS header is an irreversible
multi-year browser pin: emitting it because `env` *says* production — while the
app may actually be reached over plain HTTP behind a misconfigured proxy — is
worse than the gap. So the contract surfaces the gap and leaves the
irreversible decision to you.

**Fix:** once you have confirmed the app is only ever reached over HTTPS, set
`AppConfig(strict_transport_security="max-age=63072000; includeSubDomains")` (or
add a `SecurityHeadersMiddleware` configured with it). Either source clears the
warning. It is silent in development and staging — only the declared production
posture is nudged — and surfaces under `chirp check --deploy`.

### `password_extra`: argon2 in production

WARNING (never ERROR) when an app has a login/mutating surface (the same
`is_mutating_route` definition `security_stack` owns) **and** `argon2-cffi` is not
importable — so password hashing falls back to stdlib scrypt. scrypt is a correct,
always-available fallback (no hash is ever rejected and `verify_password`
auto-detects the algorithm from the PHC prefix), but argon2id is the recommended
algorithm for new production deployments.

This is a posture **advisory**, never an ERROR: there is no correctness gap to
fail loud on, and existing scrypt hashes upgrade to argon2 on the next successful
login via `verify_and_upgrade()` once the extra is installed. Severity is
env-aware — silent in development (and the scrypt-only base CI environment),
WARNING in staging/production — so dev apps and shipped examples stay clean, and
it escalates under `chirp check --deploy`. argon2 availability is read via the
same `_has_argon2()` predicate the runtime uses to pick the hashing algorithm, so
the check and the runtime never disagree.

**Fix:** `pip install chirp[auth]` (pulls in `argon2-cffi`). New hashes then use
argon2id; existing scrypt hashes re-derive to argon2 the next time each user logs
in if you wire `verify_and_upgrade()` (see
[[docs/quality/deployment/auth-hardening|Auth Hardening]]).

### `auth_middleware`: auth-declaring routes need `AuthMiddleware`

A route can declare that it needs authentication two ways, and **both** call
`get_user()` — which raises `LookupError` → a **500 at request time** when
`AuthMiddleware` is absent from the stack:

- **`RouteMeta.auth`** on a filesystem page (`_meta.py`): `None` / `"none"` /
  `"optional"` are open; `"required"` requires an authenticated user; any other
  non-empty string is treated as a single required **permission**.
- **`@login_required` / `@requires`** on an `@app.route` handler. These
  decorators carry a static `_chirp_requires_auth` marker on the handler the
  router stores, so the check can prove the route is auth-gated without executing
  it.

When **any** auth-declaring route exists and no `AuthMiddleware` is registered,
this fires, naming a concrete offending route and the fix (register
`AuthMiddleware` after `SessionMiddleware`).

**Env-severity matrix.** Mirrors `security_stack` — the dev 500 surfaces the gap
locally, so a standing dev WARNING would be noise:

| Condition | development | staging | production |
|---|---|---|---|
| Auth-declaring route + no `AuthMiddleware` | silent | WARNING | ERROR |
| Dynamic `meta()` page + no `AuthMiddleware` | INFO | INFO | INFO |

**Dynamic `meta()` pages are a static blind spot.** A page whose `_meta.py`
defines `meta()` resolves its auth value at runtime, so its requirement is
invisible to a static check. Those pages are **never** false-ERRORed; instead,
when `AuthMiddleware` is absent and such pages exist, a single **INFO** notes
that auth wiring could not be statically verified — wire `AuthMiddleware` if any
dynamic-meta page is gated. This mirrors how `route_contract`'s section-coverage
check handles meta providers.

**Fix:** register `AuthMiddleware` after `SessionMiddleware`
(`app.add_middleware(AuthMiddleware(AuthConfig(load_user=...)))`). It is silent
in development and escalates under `chirp check --deploy`.

### `auth_spec`: declared permissions/policies that silently fail

`RouteMeta.auth` treats any non-reserved string (and every `AuthSpec.permissions`
entry) as a required **permission**, and an `AuthSpec.policy` as a **named policy**
resolved against the app policy registry. A wrong permission silently `403`s; an
unresolved policy name **fails loud** (`500` — a misconfiguration, not an auth
denial) — both with no other startup signal. This check has two modes.

**Registry-backed (precise).** When you declare permissions/policies during setup:

```python
app.register_permission("admin")
app.register_permission("editor")
app.register_policy("is_owner", lambda user, request: ...)
```

every `RouteMeta.auth` permission **not** in the permission registry is an ERROR,
and every `AuthSpec.policy` **not** in the policy registry is an ERROR. The
registry is the source of truth, so even a plausible-looking `"admni"` typo is
caught.

**Permissions and policies are checked asymmetrically.** Permission validation is
**opt-in**: it only runs when a permission registry is declared (otherwise the
heuristic below applies). Policy validation is **always on**: a referenced
`AuthSpec.policy` name that is not registered is **always** an ERROR — even with
no policy registered at all — because an unregistered policy name unconditionally
`500`s at request time, so there is no false-positive risk.

**Heuristic-only (no permission registry).** With no permission registry declared,
permission validation falls back to a **high-signal** reserved-token-confusion
heuristic. A near-miss of
a reserved token — `"Required"`, `"REQUIRED"`, `" required "`, `"None"`,
`"Optional"`, or a tight misspelling like `"requied"` — silently becomes a
*permission named that exact string* and **403s forever** instead of gating as
intended. Empty-after-strip / whitespace-only auth (`"   "`) is the same bug. It
flags exactly:

- a case/whitespace variant of a reserved token (`"Required"`, `" required "`,
  `"None"`, `"Optional"`);
- a tight misspelling of `"required"` (edit distance ≤ 2, e.g. `"requied"`); and
- empty-after-strip / whitespace-only.

Plausible permission names (`"admin"`, `"editor"`, `"billing.read"`) are **not**
flagged in heuristic mode — without a registry Chirp cannot know which strings are
real permissions, and false positives erode trust. Declare a permission registry
to validate them precisely.

**Severity** is env-aware (silent dev / WARNING staging / ERROR prod), same as
`auth_middleware`, and escalates under `chirp check --deploy`. Dynamic `meta()`
pages are skipped (their auth value is not statically known).

**Fix:** declare the permission with `app.register_permission()` (or fix the typo),
register the policy with `app.register_policy()`, or use the exact reserved token
(`"required"` / `"none"` / `"optional"`).

### `sse_auth_gate` / `sse_context`: reading the user inside an SSE generator

`get_request()`, `get_user()` / `current_user()`, `get_csrf_token()`, and `g`
work inside an `EventStream` generator — the request-scoped context is captured
at connect time and re-established for the lifetime of the stream. Two checks
guard the two ways this can surprise you.

**`sse_auth_gate` — the user is `AnonymousUser` without `AuthMiddleware`.** An
`EventStream` generator that calls `get_user()` / `current_user()` resolves the
connect-time-captured user, but only when `AuthMiddleware` is wired. Without it,
the captured user is `AnonymousUser` for the entire stream, so an auth-sensitive
feed silently serves the anonymous view to everyone — no error, no startup
signal. Env-aware, mirroring `auth_middleware`:

| Condition | development | staging | production |
|---|---|---|---|
| SSE generator reads the user + no `AuthMiddleware` | silent | WARNING | ERROR |

**`sse_context` — the SSE user identity is pinned at connect time.** This is a
**post-fix semantic nudge, never an ERROR** — the pattern WORKS. When a generator
reads the user inside a **long-lived loop** (`while` / `async for` / `for`), the
identity is fixed for the connection's lifetime: a mid-stream logout or
permission revoke is **not** reflected until the client reconnects. It fires as a
`WARNING` in staging/production (silent in development) so you can decide whether
the feed is auth-sensitive enough to re-check authorization per event (or close
the stream on revoke). A short-lived top-level user read (outside any loop) is
*not* nudged — it resolves once and the stream ends.

::::{warning} Static-analysis scope: inline and module-level generators only
Both rules resolve the generator passed to `EventStream(...)` in **two** scopes:

1. an **inline** nested `async def generate()` defined inside the route handler
   (the common case), and
2. a **module-level** `async def gen()` passed as `EventStream(gen())`, resolved
   by name through the handler's `__globals__`.

A generator built by any **other indirection** — a factory function, a method,
a value threaded through another call, or a comprehension — is **not** statically
resolvable and is **silently skipped**. This is a deliberate false-NEGATIVE: the
rules err toward silence so they never raise a false ERROR, but they are **not**
complete coverage. If your SSE handler reads the user through an indirected
generator, wire `AuthMiddleware` and re-check per-event authorization manually —
neither check will catch the gap for you.
::::

These rules do not fire on the shipped `chat` / `kanban` / `dashboard` /
`lucky_cat` SSE examples: their generators read **global** state (the message
bus, the task store, the market feed), never the request user.

## Data

| Category | Default severity | Fix target |
|---|---|---|
| `data` | ERROR | Fix `db.fetch(cls, sql)` / `fetch_one` / `stream` SELECT columns that map to no field on the target frozen dataclass. See the dropdown below for what it fires on. |
| `shapecheck` | ERROR / WARNING / INFO | Verify the *render* side of `@shape`-decorated row models. See the dropdown below for the four checks and escape hatches. |

::::{dropdown} `data` — what the static query check checks
The check is static and conservative: it only fires when the `cls` argument
resolves to a module-level frozen dataclass **and** the SQL is a string literal
with an explicit `SELECT a, b` list. `SELECT *`, expressions, aggregates,
dynamic SQL (f-strings, concatenation), and computed `cls` are skipped silently —
no false positives.

A SELECTed column is flagged only when it is absent from the dataclass fields
**and** (when a declared schema is available from a `migrations` directory)
absent from every declared table column — that double-guard keeps the check
quiet for columns the dataclass intentionally does not read. HTML-only / db-less
apps (no `migrations` dir) emit no `data` issues. Overridable via
`app.override_contract_severity("data", Severity.WARNING)`.

The `data` category owns only the *query* axis (SELECTed-column-vs-dataclass-field
on raw `db.fetch` calls); it never fires on `Shape.fetch(...)` (whose receiver is
the `Shape` class, not a db handle), so it cannot double-fire with `shapecheck`.
::::

::::{dropdown} `shapecheck` — the four checks and the escape hatches
`shapecheck` verifies the render side of `@shape`-decorated row models
(`chirp.data`) — see [[docs/build-apps/forms-data/shapes|shapes and the @shape render contract]]. Four
statically-decidable claims, all overridable via
`app.override_contract_severity("shapecheck", ...)`.

**ERROR** covers three claims:

1. **Registry drift** — a surface-contract name
   (`set_contract_check_data("surface_contracts", {...})`) whose target resolves
   to no registered Shape (the marquee check; runs even with no contract data via
   the auto `shape_registry()`, and suggests the closest registered name).
2. **Under-fetch** — a block reads `shapevar.field` (single-object access) where
   `field` is neither a SELECT column nor a declared `computed=` member of the
   bound Shape, so it silently renders as `None`.
3. **Un-injectable tenant scope** — a Shape used by the app declares `scope=`
   (e.g. `@shape("SELECT ...", scope="community_id")`) but its SQL is opaque /
   un-injectable (CTE / UNION / `SELECT *` / no analyzable FROM), so the bounded
   compiler cannot structurally inject the scope predicate and the query would
   silently read across tenants. (The scope guarantee itself is unconditional:
   when injectable, the compiler always adds `community_id = :scope` to the parent
   SELECT and every batched child `IN`-list query, asserted on the compiler
   *output* by `Shape.validate`, not by a WHERE-column scanner — so the only
   decidable scope failure is the un-injectable case.)

**WARNING** is **over-fetch** — a Shape column no bound block reads; block
coverage is incomplete static information, so it is humble by default and
promotable.

**INFO** is the **PASS line** — one `PASS shapecheck: N verified` issue when N>0
bindings verified clean and no ERROR fired.

Blocks are bound to Shapes by AST-parsing the handler's `Fragment` / `Page` /
`Suspense` return (the block is the second positional; a kwarg whose value
resolves to `Shape.fetch(SomeShape, ...)` or a `@shape` class names the template
variable), with `set_contract_check_data("shapecheck_bindings", {(template, block): ShapeClassOrName})`
as the explicit fallback.

**Escape hatches — `shapecheck` is silent on all of these:**

- template globals (`url_for`, `csrf_token`, `csp_nonce`, `_`, `range`, `len`, …);
- block-local bindings (`{% set %}` / `let` / `export` / `capture` / `def` /
  `region` / loop targets / def params);
- the literal context keys `error` and `form`;
- **derived accessors on the Shape dataclass** — a `shapevar.name` read where
  `name` is a real class-level attribute (a `@property`, method, or descriptor) on
  the bound dataclass but not a dataclass field (`{{ person.full_name }}` over
  `first_name`/`last_name`, `{{ article.url() }}` over `slug`); these resolve at
  runtime so they never under-fetch, and because the columns they consume live
  *inside* the accessor body (invisible to `depends_on`) a derived-accessor read
  in any binding of the Shape also suppresses the over-fetch claim for that Shape;
- loop-collapsed reads (only the collection root appears in `depends_on`, never
  `root.field` — the dominant list/table pattern);
- macro / def-arg reads;
- opaque shapes (`SELECT *`, expressions, CTE/UNION → `columns == ()`);
- deeper dotted segments (`v.a.b` checks only `a`, never `b` — so
  `{{ board.title.upper() }}` checks only the `title` column);
- templates under `chirp/` / `chirpui/`.

No-op when `kida_env` is `None` (registry drift still runs).
::::

## Debug, Extensions, Accessibility, And Plugins

| Category | Default severity | Fix target |
|---|---|---|
| `debug_wiring` | ERROR | Fix debug/DevTools route, asset, or runtime wiring so diagnostics work in debug mode. |
| `chirpui_runtime` | INFO | Call `use_chirp_ui(app)` or install/configure the optional UI runtime required by ChirpUI templates. |
| `alpine_cdn_url` | ERROR | Replace bare jsDelivr Alpine package URLs with explicit `/dist/cdn.min.js` URLs or Chirp injection helpers. |
| `defer_falsy` | WARNING | Use `{% if key is deferred %}` or `"key" in __chirp_defer_pending__` to distinguish loading from loaded before testing resolved values. See [[docs/build-apps/request-pipeline/render-plan|Suspense deferred keys]]. |
| `suspense_defer` | WARNING | A template declares a Suspense-deferred key (`is deferred` / `__chirp_defer_pending__`) that no block depends on, so auto-discovery finds nothing to re-render. Reference the key inside a `{% block ... %}`, or pass the blocks explicitly with `Suspense(..., defer_blocks=(...))`. |
| `a11y_interactive` | WARNING | Add keyboard and semantic affordances for interactive elements. |
| `a11y_label` | WARNING | Add visible or accessible labels for form controls. |
| `a11y_alt` | WARNING | Add meaningful `alt` text or intentionally empty decorative `alt=""`. |
| `a11y_heading` | WARNING | Fix skipped or incoherent heading levels. |
| `a11y_landmark` | WARNING | Add page landmarks such as `main`, `nav`, or `header` where expected. |
| `plugin_check_error` | ERROR | Fix a custom check that raised during `app.check()`; the original exception should name the plugin/check. |
| `plugin_quarantine` | ERROR | Fix the plugin whose `register()` raised during `app.mount()`. The plugin was quarantined (skipped) so the app could still boot — leaving it half-configured — and a WARNING was logged at mount time. The message names the prefix, plugin, and original error. |

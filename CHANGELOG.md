## [0.10.1] — 2026-07-14

### Fixed

- PostgreSQL TLS connections now explicitly negotiate as clients, allowing managed PostgreSQL services such as Railway to work with Pelt's default SSL mode and preserving hostname verification for `sslmode=verify-full`. ([#753](https://github.com/lbliii/chirp/issues/753))


## [0.10.0] — 2026-07-08

### Added

- Add a versioned live-PostgreSQL Pelt benchmark that reports aggregate query scaling separately from single-cursor and sequential bulk-loop performance boundaries.

### Changed

- Published Chirp's tested full-application compiler proof and aligned README, architecture, and hypermedia documentation around the shipped contract compiler, live ASGI runtime, and optional static-export boundary. ([#513](https://github.com/lbliii/chirp/issues/513))
- Moved the packaged `chirp` command tree from direct argparse registration to
  released Milo 0.4.x lazy typed commands. Existing command syntax, output
  channels, exit codes, handler laziness, and version aliases remain covered by
  the compatibility suite; Milo help and root operations are additive, and agent
  exposure remains an explicit deny-by-default allowlist. ([#572](https://github.com/lbliii/chirp/issues/572))
- Exposed the reviewed read-only `check`, `diff`, and `routes` inspections through
  Milo MCP and llms.txt. Their handlers now return stable structured values across
  programmatic and agent calls while Milo's terminal renderer preserves existing
  human output and exit behavior. Lifecycle and write-capable commands remain
  CLI-only. ([#573](https://github.com/lbliii/chirp/issues/573))
- Added a CI exception-hygiene ratchet that rejects new vague public raise messages, unjustified exception suppression, masked configuration-load failures, and silent pass/continue handlers while tracking existing findings as explicit cleanup debt. ([#620](https://github.com/lbliii/chirp/issues/620))
- Added a machine-checked public claims ledger and narrowed free-threading, benchmark, and rolling-reload language to the scope supported by committed evidence. ([#621](https://github.com/lbliii/chirp/issues/621))
- **Benchmark evidence** — the cross-framework runner can now emit a versioned JSON artifact and regenerate the documented comparison table from it, preserving environment, latency, and failed-attempt data alongside synthetic-results caveats.
- **CI coverage gate enforced** — the main test job now runs pytest with `--cov`, so the `fail_under` threshold configured in `pyproject.toml` actually fails the build instead of being decorative.
- Added FastHTML to the optional synthetic framework benchmark matrix using the same JSON, CPU, SQLite, and HTML-rendering workloads as the existing peers.
- Added a same-runner core benchmark gate that publishes pull-request comparisons and fails CI when median latency regresses by more than 20 percent or a tracked workload disappears.
- Run Pelt's real-wire conformance suite against PostgreSQL 13–18, retaining final 13.22 as an explicit EOL compatibility lane.

### Fixed

- Pelt database errors now link to a shipped troubleshooting catalog, preserve exact PostgreSQL SQLSTATE codes through a finite documented anchor, and verify the future extraction export surface. ([#260](https://github.com/lbliii/chirp/issues/260))
- Anonymous requests that do not create session state no longer emit `Set-Cookie` or write to custom session stores, restoring shared-cache and CDN eligibility while preserving existing-session refresh, timeout, CSRF, nested-mutation, and regeneration behavior. ([#618](https://github.com/lbliii/chirp/issues/618))
- **Production request limits** — Chirp now forwards `AppConfig.max_request_body_size` to Pounce, so valid bodies above Pounce's former 1 MiB default reach the application while oversized requests still receive 413 responses at the wire boundary.
- Keep Pelt server cursors memory-bounded by releasing decoded batches after iteration, and document the `data-pg` backend, libpq-free deployment model, and single-query/bulk performance limits.
- Preserve Pelt row metadata when a server-side cursor resumes, so streamed queries can cross multiple portal batches without a protocol error.


## [0.9.0] — 2026-07-07

### Added

- Published the universal-operation design boundary for projecting one typed Milo command across Chirp HTTP, htmx, CLI, MCP, WebMCP, and MCP Apps without adding automatic exposure, a parallel renderer, or a generic JSON path. ([#339](https://github.com/lbliii/chirp/issues/339))
- Added `TestClient.boosted()` and boosted route-smoke coverage that distinguishes negotiated `Page` shell outlets from unsafe full-page `Template` responses. ([#497](https://github.com/lbliii/chirp/issues/497))
- Added a self-validating example inventory that records support status, dependencies, network needs, capabilities, README coverage, and test entrypoints for every runnable example. ([#501](https://github.com/lbliii/chirp/issues/501))
- Published the structured application-inspection design for one immutable result shared by Python consumers, terminal checks, versioned JSON, and contract diff tooling while preserving the existing CLI JSON contract. ([#510](https://github.com/lbliii/chirp/issues/510))
- Added stable compiled-transition IDs and public-safe descriptions to debug return traces, DevTools exports, and testing coverage helpers so normal, boosted, targeted, mutation, OOB, Suspense, and SSE paths can share runtime evidence. ([#511](https://github.com/lbliii/chirp/issues/511))
- **Full-application journey** — connect the maintained Todo, Kanban Shell, Dashboard Live, Lucky Cat, and Freeze Site examples into one tested path from SQLite and dual-mode forms through boosted navigation, OOB, Suspense, SSE, contract diagnostics, deployment, and optional static projection. ([#512](https://github.com/lbliii/chirp/issues/512))
- Added experimental RFC 10008 QUERY request enforcement for explicit routes through `App.route(..., methods=["QUERY"], query_media_types=(...))`, with freeze-time media-range validation, ASGI-only dispatch, body-limit parity, and actionable 400/406/413/415/422 behavior. Existing bare `methods=["QUERY"]` routes must add a non-empty media declaration before freeze. ([#525](https://github.com/lbliii/chirp/issues/525))
- Added path-scoped HTTP QUERY discovery and response semantics: generated 405/OPTIONS responses advertise `Allow` and structured `Accept-Query`, existing Redirect/Response headers represent opaque equivalent resources, and ordinary GET/QUERY responses share ETag and Last-Modified evaluation without introducing new public helpers. ([#526](https://github.com/lbliii/chirp/issues/526))
- Added executable HTTP QUERY rendering and DevTools proof across Page, Fragment, OOB, Stream, Suspense, validation, and redirects. Debug traces now include the request method and content type, while DevTools identifies programmatic QUERY requests as safe and records their selected render path, timing, and errors. ([#529](https://github.com/lbliii/chirp/issues/529))
- Added a collision-safe provisional HTTP QUERY cache-key design that hashes exact request bodies and representation metadata without exposing raw content, preserves handler body reads and private-request bypass, and leaves QUERY cache reads and writes disabled pending the separate opt-in gate. ([#530](https://github.com/lbliii/chirp/issues/530))
- Added explicit HTTP QUERY response caching through `CacheMiddleware(query_key_func=...)`, with default-off behavior, private and streaming bypass, preserved render metadata, conditional-hit validators, backend fail-open handling, and actionable optional Redis installation guidance. ([#531](https://github.com/lbliii/chirp/issues/531))
- An exact, reversible htmx 4.0.0-beta5 preview now provisions core, htmx-2-compat, and hx-sse in nonce-safe order, with fail-loud compatibility checks and DevTools diagnostics; htmx 2.0.10 remains the default and rollback baseline. ([#545](https://github.com/lbliii/chirp/issues/545))
- `app.check()` now reports line-aware htmx 2/4 provisioning and template drift, including version-specific attributes, lifecycle events, configuration keys, extension dialects, and implicit inheritance. A pinned optional upstream inventory command retains migration evidence without adding a runtime dependency. ([#547](https://github.com/lbliii/chirp/issues/547))
- Added a machine-verified CLI compatibility contract covering every command,
  flag, default, output channel, exit policy, structured mode, lazy-import
  boundary, and agent-exposure decision before the planned Milo migration. ([#571](https://github.com/lbliii/chirp/issues/571))
- Add an explicit experimental `WebMCPForm` projection that renders safely escaped declarative browser-tool attributes from frozen dataclass form contracts while preserving ordinary HTTP, htmx, validation, and CSRF behavior. ([#574](https://github.com/lbliii/chirp/issues/574))
- Add ERROR-only `app.check()` diagnostics and structured coverage/diff counters for malformed, drifting, or unsafe experimental WebMCP form projections. ([#575](https://github.com/lbliii/chirp/issues/575))
- Add a Chrome 149 progressive-enhancement lane and authenticated, unauthorized, expired-session, CSRF, adversarial-input, confirmation, and htmx parity proof for experimental WebMCP forms. ([#576](https://github.com/lbliii/chirp/issues/576))
- **Dynamic template reachability** — use `app.declare_template(template, blocks=(...))` during setup when a registry selects templates or named blocks at runtime. Chirp normalizes surrounding name whitespace, `app.check()` validates every declared name, and the declaration records the call-site origin without suppressing unrelated dead-template warnings.

    **Migration** — replace unreachable `if False: Page(...)` or `Fragment(...)` reference stubs with the matching `app.declare_template(...)` call.
- Release CI now reports an advisory compatibility canary that installs the built Chirp wheel into a pinned, locked Furatena checkout and exercises its framework-facing integration paths.

### Changed

- Pelt now drains failed query exchanges through `ReadyForQuery` before raising, so pooled connections reliably roll back failed transactions before reuse. Its free-threading contract also has no-GIL contention and decode-overlap gates, live PostgreSQL pool/cache proof, and an auditable evidence map; current database docs identify the in-tree pure-Python driver instead of the retired asyncpg backend. ([#259](https://github.com/lbliii/chirp/issues/259))
- Added reproducible browser, Pounce HTTP/1.1/2/3, Uvicorn, Nginx, retry, redirect, body-limit, and body-redacted access-log, metric, and trace evidence for experimental HTTP QUERY deployments. ([#532](https://github.com/lbliii/chirp/issues/532))
- Published the experimental HTTP QUERY adoption guide, compatibility matrix, GET-first guidance, deployment and cache boundaries, migration notes, and release decision: controlled early-adopter use is documented, while stable promotion remains gated on client/pages ergonomics, static diagnostics, and the canonical example. ([#535](https://github.com/lbliii/chirp/issues/535))
- Chirp DevTools, islands, safe-target processing, and View Transitions now consume both htmx 2 lifecycle events and htmx 4 fetch-era events. Request-context correlation prevents duplicate diagnostics and island effects when the `htmx-2-compat` extension emits both event names. ([#542](https://github.com/lbliii/chirp/issues/542))
- The verified htmx 2.x baseline is now 2.0.10. AppConfig.htmx_version, managed injection, first-party layouts, scaffolds, examples, tests, and source-site docs now use the explicit jsDelivr /dist/htmx.min.js browser bundle. ([#543](https://github.com/lbliii/chirp/issues/543))
- Signals now follow the selected htmx client tier: htmx 2 retains named SSE
  events and `sse-swap`, while the exact htmx 4 preview uses one native
  `hx-sse:connect` and unnamed `<hx-partial>` updates targeting every matching
  `data-chirp-signal` sink. ([#544](https://github.com/lbliii/chirp/issues/544))
- Request htmx metadata now normalizes htmx 4 `tag#id` targets and sources alongside htmx 2 headers, exposes validated `HX-Request-Type`, varies negotiated pages by request type, and extends `TestClient` with htmx 4 request metadata helpers. ([#546](https://github.com/lbliii/chirp/issues/546))
- The exact htmx 4 preview now declares safe browser defaults before core: 4xx fragments swap, broad 5xx responses do not, requests time out after 60 seconds, history refetches server HTML, OOB updates are main-first, DELETE form data is explicit, and queues use `hx-sync`. `app.check()` and DevTools diagnose dangerous drift with browser regression proof. ([#548](https://github.com/lbliii/chirp/issues/548))
- Htmx 4 preview requests now fail before send when a response contains removed `HX-Trigger-After-Swap` or `HX-Trigger-After-Settle` headers. Htmx 2 and generic wire behavior remains unchanged; preview applications migrate to rendered target data and per-target settle lifecycle events. ([#549](https://github.com/lbliii/chirp/issues/549))
- The exact htmx 4 preview now gives `EventStream` a native, connection-fixed SSE dialect: rendered fragments use unnamed HTML and validated `<hx-partial>` targets, named `SSEEvent` values remain DOM events, `sse_scope()` emits `hx-sse:connect`, and tests and DevTools expose the selected wire contract. Htmx 2 and generic SSE behavior remains available during migration. ([#553](https://github.com/lbliii/chirp/issues/553))
- Newly generated projects now require `bengal-chirp>=0.9.0`, keeping scaffold dependency metadata aligned with the framework version that produced it.
- Raised the required `kida-templates` version to `>=0.11.0`, the framework-integration checkpoint with unchanged runtime API and template syntax, so Chirp releases against Kida's current tested component and free-threading baseline.

### Fixed

- The documented development environment now installs the passkey dependency needed to collect and run the complete example test suite.

  The todo example now uses `Page` return-type negotiation instead of manually branching on htmx request state. ([#499](https://github.com/lbliii/chirp/issues/499))
- HEAD requests now select explicit HEAD routes or fall back to GET routes, advertise HEAD wherever GET is allowed, and require bengal-pounce 0.8.2 so dynamic responses retain GET-equivalent metadata while sending no body bytes. Applications that relied on GET-only routes rejecting HEAD with 405 should register an explicit HEAD route for their policy. ([#554](https://github.com/lbliii/chirp/issues/554))
- Fixed a circular import that prevented direct imports of the server negotiator and clean-process runs of the core benchmark.


## [0.8.2] — 2026-06-25

### Added

- The `@login_required` and `@requires` decorators now carry a static `_chirp_requires_auth = True` marker on the returned wrapper, so `app.check()` and other contract introspection can prove an `@app.route` handler is auth-gated without executing it. The decorators preserve `functools.wraps`, so `inspect.unwrap` still reaches the inner handler while the marker stays on the outermost wrapper the router stores. Purely additive and invisible to callers — no signature or behavior change. ([#auth-decorator-static-marker](https://github.com/lbliii/chirp/issues/auth-decorator-static-marker))
- Request now exposes ergonomic request-scoped auth and session accessors, and templates get a session-safe `session()` global. `request.user` returns the current user (or `AnonymousUser`) and never raises, mirroring `current_user()`. `request.session` returns the session dict and raises `LookupError` when `SessionMiddleware` is absent, mirroring `get_session()`'s fail-loud contract — so `request.session.get("x")` works without a `None` footgun. In templates, `session()` returns the live session dict when `SessionMiddleware` is active or an empty read-only mapping otherwise (never raises), and is auto-registered as a template global only when `SessionMiddleware` is present. ([#request-user-session-accessors](https://github.com/lbliii/chirp/issues/request-user-session-accessors))
- **Signals (#317):** `signal_connect()` now finalizes a scoped `/_chirp/live?topics=…` URL at end-of-render from runtime binding tracking, so async sources pump only for bound topics and derived dependencies. Optional proactive activation via `app.set_signal_prefix_topics({"/prefix": ("signal", …)})`.
- **Auto-mounted `/health` (liveness) + `/ready` (readiness) ops probes.** Every Chirp app — including the `chirp new --minimal` scaffold — now serves two Kubernetes-style probes with no hand-wiring. **`/health`** always returns plain `200 ok` (K8s `livenessProbe`). **`/ready`** returns `503` until startup completes (db connect, migrations, and all `@app.on_startup` hooks), then runs every registered readiness check, returning `503` plus the failure list on any failure and plain `200 ready` otherwise (K8s `readinessProbe`; the LB rotation gate). Both probes **short-circuit before the secure middleware stack** (Session/CSRF/SecurityHeaders) and the commit teardown — they run no user handler, set no cookie, never touch the session — and return plain text outside return-type negotiation.

  Register dependency checks before freeze with `app.add_health_check(HealthCheck("cache", check=ping_cache))` (the `check` callable may be **sync or async**); `HealthCheck` is now a top-level export (`from chirp import HealthCheck`). When a database is wired, a `Database.probe()`-backed check is auto-included — a `SELECT 1` on a **fresh pooled connection** (never the request session, dodging the poisoned-session footgun) — so `/ready` reflects DB connectivity for free.

  New frozen `AppConfig` fields **`health_path`** (`"/health"`, `CHIRP_HEALTH_PATH`) and **`ready_path`** (`"/ready"`, `CHIRP_READY_PATH`) set the probe paths. A user route claiming a probe path wins (the probe steps aside), and a new `deploy_health` `app.check()` ERROR category flags that collision so it never happens silently. `Database.probe()` (new, async) and `chirp.health.readiness()` (now async, awaiting sync-or-async checks) round out the surface. See `site/content/docs/quality/deployment/production.md` and `site/content/docs/quality/contracts-debugging/categories.md`.
- **Structured logging — trace context + framework JSON formatter** (internal). `structured_log()` now best-effort enriches each payload with `trace_id` / `span_id` read from the active OpenTelemetry span (`opentelemetry.trace.get_current_span()`) behind a guarded import — Chirp adds **no** opentelemetry dependency, so logs join the trace pillar when OTel is configured (via `AppConfig.otel_endpoint`, delegated to the server) and are unchanged otherwise. An invalid/no-op span, an absent opentelemetry, or a misbehaving tracer all skip silently and never raise out of logging. When `AppConfig.log_format == "json"`, freeze installs a crash-proof `JSONFormatter` on the `"chirp"` logger once and idempotently (scoped to that logger, never `logging.basicConfig`, `propagate=False` to avoid double-emit through the server's root handler) so Chirp's own log lines match the server (Pounce) JSON envelope. `CHIRP_LOG_LEVEL` is now read by `AppConfig.from_env` onto the existing `log_level` field (env parity with `CHIRP_LOG_FORMAT`; no new field).

    **SSE blind spot:** the SSE drain re-establishes request context from a captured snapshot and does **not** `copy_context`, so trace context survives buffered, `Suspense`, and `Stream` renders but **not** logs emitted from inside an `EventStream` (SSE) generator. SSE span-context parity is a deferred follow-up alongside the existing per-event SSE revalidation deferral.
- **`app.add_middleware(mw, priority=...)`** makes the request pipeline order explicit and independent of registration order. The user middleware is sorted *once* at freeze by `(priority, registration_order)` — a **stable** sort, so equal-priority middleware keep their registration order and an all-default-priority stack resolves byte-identically to today's append order (lower priority runs **outermost**, wrapping the rest). Built-in middleware (allowed-hosts, CSP nonce, security headers, injection, …) stays positionally pinned around the user chain. The hard floor is unchanged: a `priority` that would place `CSRFMiddleware` outside `SessionMiddleware` still raises `ConfigurationError` at freeze, and the `csrf_session` ERROR check now evaluates the *freeze-resolved* order so a priority-induced misordering can no longer slip past it. A new **`middleware_chain`** `app.check()` category (INFO, diagnostic only) reports the resolved user middleware order so authors can confirm the pipeline they registered is the pipeline that runs. See `site/content/docs/quality/contracts-debugging/categories.md`.
- **`json_path(column, *keys, dialect)`** (`chirp.data`) and the bound **`Database.json_path(column, *keys)`** convenience wrapper build a dialect-correct JSON-extraction SQL expression fragment — `json_extract(oauth, '$.sub')` on SQLite, `oauth->>'sub'` on PostgreSQL (nested keys: `data->'a'->>'b'`). Drop the result straight into a `Query.where()` / raw-SQL string so the sqlite-vs-postgres branch stops leaking into every call site; the fragment is a static expression with no bound-parameter placeholder of its own, so keep filter values as separate bound params and never pass request/user-controlled values as the column or keys.
- **`secure_stack(config)`** — a one-call helper (`chirp.middleware.stack`) that returns the secure-by-default middleware list in the contract-passing order: `[SessionMiddleware, CSRFMiddleware, SecurityHeadersMiddleware]`. Wire the whole stack in one line — `for mw in secure_stack(app.config): app.add_middleware(mw)` — while staying explicit-over-magic: it is a pure list-returning function (nothing is force-injected, and the caller still adds each middleware). It reads `secret_key` from the app config and leaves the session cookie's `Secure` flag as the blessed `secure="auto"` default, so the cookie's secure posture is derived at freeze from `config.env` (Secure for staging/production) — never from `config.debug`. Pass `session=`/`csrf=`/`headers=` to override any leg, or `redis_url=` to back sessions with `RedisSessionStore`. The generated stack passes the `security_stack` and `csrf_session` `app.check()` contracts out of the box.
- Add MCP tool ``chirp_surface_diff`` via ``register_surface_diff_tool()`` for agent-facing hypermedia contract diffs.
- Add SessionSignalMiddleware, signal_bind(), SignalEmit return type, and DevTools signal-emit tracing for mutation handlers.
- Add `chirp diff APP --base REF` to compare hypermedia contract reports against a git base ref.
- Add advisory PR comments for hypermedia contract diffs via `.github/workflows/contract-diff.yml`.
- Add chirp-ui cross-version CI release gate matrix job.
- Add contract JSON baselines and diff support to ``chirp check``.
- Add pelt E4 transport/auth I/O edge: ``RecvBuffer``, TLS sslmode negotiation, SCRAM-SHA-256/MD5/cleartext auth, session handshake driver, and cancel-request helper.

  Closes #325, #326, #327, #328, #329, #330. Closes #253, #254.

  Acceptance: n/a (#253, #254 epics — all child issues already shipped with acceptance tests).
- Add pelt E6 free-threading runtime probes, parallel row decode, and concurrency stress tests.
- Declarative auth (`RouteMeta.auth` / `AuthSpec`) gained app-level permission and policy registries plus a registry-backed startup check. `app.register_permission(name)` declares a permission and `app.register_policy(name, fn)` registers a `(user, request) -> bool` policy callable that a declarative `AuthSpec(policy=name)` resolves by name at request time (an unregistered policy name fails loud — 500). Both are setup-only (raise `RuntimeError` after freeze). With a permission/policy registry declared, the `auth_spec` contract check becomes precise — a `RouteMeta.auth` permission not in the registry, or an `AuthSpec.policy` not in the policy registry, is an env-aware ERROR (escalates under `chirp check --deploy`); with no registry it keeps the high-signal reserved-token-typo heuristic. `RouteMeta.auth` is now normalized to a canonical `AuthSpec | None` at discovery time, and **dynamic `meta()` results that return structured `auth` (a dict or `AuthSpec`) are now enforced identically to static `META`** — previously a dynamic `meta()` auth value was silently dropped. A `dict` auth value (e.g. `{"permissions": ["a", "b"], "mode": "any"}`) constructs an `AuthSpec`.
- Headline islands as the no-build answer for client state and ship the blessed ``optimistic_apply`` primitive (with the ``optimistic_attrs()`` template global). It paints a mutation locally and instantly from the client's own pre-mutation snapshot, lets htmx do the real request, swaps the authoritative server fragment on success (last-write-wins), and reverts to the snapshot only when no authoritative fragment lands — holding **zero per-client server view state**. The zero-server-state boundary is machine-checked by the ``TestOptimisticApplyGuardrail`` gates, and islands metadata ERROR checks (including the new ``optimistic_apply`` op/forbidden-key validation) run by default in ``app.check()``. See ``examples/standalone/optimistic_apply/``. Closes #153.
- Migrations now fail loud when an already-applied migration file is edited in place. `migrate()` records a `sha256` of each migration's SQL in a new nullable `checksum` column on the `_chirp_migrations` tracking table, and on every run raises `MigrationError` (naming the file, before applying anything) when an applied migration's on-disk SQL no longer matches its recorded checksum — closing a silent data-corruption footgun where "fixing a typo" in a shipped migration was ignored forever. Rows written by a pre-checksum Chirp version have a `NULL` checksum and are treated as legacy (skip-verify); the column is added idempotently to existing tracking tables. Applied migrations are immutable: write a new forward migration instead of editing a shipped one. No public API change — `migrate(db, directory)`'s signature is unchanged.
- New `AppConfig.skip_migrations: bool = False` (env: `CHIRP_SKIP_MIGRATIONS`) and a `chirp migrate` CLI command let multi-instance deploys run schema migrations as a one-shot pre-deploy job instead of racing on startup. `skip_migrations=True` gates the on-boot migration run in the app lifecycle — when migrations are present but skipped, the app logs a `lifecycle:migrations-skipped` warning so a missing deploy job (and the resulting stale schema) is visible. `chirp migrate --db <url> --migrations-dir <dir>` mirrors the sibling `chirp makemigrations` flag surface, applies pending migrations via the existing `migrate()` runner, prints the result summary, and is fail-loud (a failed migration, an invalid directory, or a checksum-drift edit of a shipped migration exits `1`). It deliberately does **not** import or boot the app (no freeze, no contract checks). Pair the env var with the command in your deploy (e.g. Railway pre-deploy) so a single job owns migration application. See `site/content/docs/reference/cli.md` and `docs/deployment/railway.md`.
- New `app.check()` category **`password_extra`**: a deploy-posture advisory that WARNs (in staging/production, silent in development) when an app has a login/mutating surface but `argon2-cffi` is not installed, so password hashing falls back to stdlib scrypt. It recommends `pip install chirp[auth]` for argon2id in production and notes that existing scrypt hashes upgrade on the next successful login via `verify_and_upgrade()`. argon2 availability is detected via the same `_has_argon2()` predicate the runtime uses to pick the hashing algorithm — not a middleware class name — so the check and the runtime never disagree. It is never an ERROR (scrypt verifies and stores correctly, so there is no correctness gap), is env-aware, escalates under `chirp check --deploy`, and reuses the canonical `is_mutating_route` definition (`security_stack`) so a GET-only filesystem page backed by `_actions.py` form actions still counts as a login/mutating surface. The shipped login examples (`examples/standalone/auth`, `examples/standalone/kanban`, `examples/chirpui/lucky_cat`) and the `chirp new` scaffold now call `verify_login(...)` instead of the `if user and verify_password(...)` short-circuit, so generated and example apps are user-enumeration-safe by default. See `site/content/docs/quality/contracts-debugging/categories.md` and `site/content/docs/quality/deployment/auth-hardening.md`.
- New `chirp.security` helper `resolve_permissions(group_blobs, *, base=frozenset()) -> frozenset[str]` (`from chirp.security import resolve_permissions`). Chirp's authorization gate resolves against a **flat** `user.permissions` frozenset and assumes something upstream flattened the user's groups — this is that flattener. It OR-merges (most-permissive-wins set **union**, never intersection) a user's per-group permission blobs and flattens nested truthy-leaf mappings (`{"billing": {"read": True, "write": False}}` -> `{"billing.read"}` — falsy leaves grant nothing) into the flat set the existing exact-match gate consumes unchanged. Each blob may be either an already-flat `Iterable[str]` (passed through) or a nested `Mapping` (flattened to dotted keys), so apps with either storage shape can wire it straight into their own `load_user`. Pure stdlib, no DB-backed Group/User model — persistence stays the app's choice (BYO-user Protocol, no-ORM). The returned `frozenset` is immutable and the function holds no shared state, so it is thread-safe by construction. Matching stays **exact**: a held `"billing"` does not cover a required `"billing.read"` (dotted-prefix coverage widens authorization and is deferred to a separate opt-in issue).
- New opt-in `AuditMiddleware` (config: frozen `AuditConfig`) emits one per-request who/what/when/status audit trail through the **existing** `emit_security_event` sink under an `http.request` namespace — so general request auditing and auth/CSRF telemetry stay one pipeline. It is OFF by default (`AuditConfig.level="none"`); raise `level` to `"metadata"` (method/path/`status_code`/`source_ip`/`user_agent`/`user_id` in `details`), `"request"` (adds a byte-capped, redacted request-body snapshot), or `"request_response"`. Only `audited_methods` are trailed (default `MUTATING_METHODS` — POST/PUT/PATCH/DELETE). Redaction is config-driven: `redact_keys` (default `password`/`token`/`secret`/`csrf_token`, case-insensitive form-key masking) and optional `redact_patterns` regex masking. Source IP comes from `request.trusted_client_ip` (trusted-proxy-corrected, never a spoofable re-parsed `X-Forwarded-For`). **Hypermedia-safe:** for `Stream`/`Suspense`/`EventStream` return types (resolving to `StreamingResponse`/`SSEResponse`/`FileResponse`) it downgrades to metadata-only and never drains the request body. Wire it via `app.add_middleware(AuditMiddleware(AuditConfig(...)))` or as the new outermost `secure_stack(app.config, audit=AuditConfig(...))` leg. Exported from `chirp.middleware`.
- Passkey / WebAuthn support — a thin ceremony codec over `py_webauthn` plus a vendored JS bridge, gated behind the optional `chirp[passkeys]` extra (`webauthn>=2.8,<3`; deliberately not in `all`/`full`). `chirp.security.passkeys` (sub-module, not a top-level export — the `hash_password`/`verify_password` precedent) exposes `PasskeyConfig`, the `PasskeyCredential` store protocol (BYO row, like `User`), and the four begin/finish verbs (`begin_registration`/`finish_registration`/`begin_authentication`/`finish_authentication`). The framework owns the **verb** and the session-bound challenge lifecycle; the app owns the **row**. The challenge is single-use, carries an embedded TTL (the session has no per-key TTL), and is **popped before verification** — so `login()` → `regenerate_session()` (which clears the session) can never wipe a not-yet-consumed challenge; the verbs never call `login()`, so passkeys terminate in the same single `login(user)` path as passwords. Verification is fail-closed: `py_webauthn`'s `verify_*` raise on any mismatch, and the verbs re-raise a generic `PasskeyVerificationError`/`PasskeyChallengeError` without leaking which check failed. `PasskeyConfig` validates the rp_id-is-a-registrable-suffix-of-origin invariant at construction (the WebAuthn footgun that otherwise throws an opaque browser `SecurityError`). `AppConfig(passkeys=True)` injects `window.chirp.passkeys` — a dependency-free, inline, nonced `register`/`authenticate` bridge (SimpleWebAuthn-parity, native `toJSON`/`parse*FromJSON` with a base64url fallback, DOMException→clean-state mapping) via `HTMLInject`, deduped on `data-chirp="passkeys"`. A new env-aware `passkeys` `app.check()` category fires an env-independent ERROR when `passkeys=True` without `webauthn` installed and a production/staging WARNING for the cookie-store challenge-bloat footgun. Missing `webauthn` fails loud at first use with a `ConfigurationError` (no stdlib fallback).
- Per-record access grants ship via ``access_grants`` table helpers, ``Query.accessible_to`` for set-based list filtering, ``access_policy`` / ``register_access_policy`` for the named-policy seam, and ``create_grant`` with fail-loud sharing-escalation validation. ``ReactiveBus.close_user`` and ``app.kick_user`` terminate a user's live SSE streams so reconnect re-pins auth after revocation. An env-aware ``access_grant_scalar_loop`` contract check flags per-row ``check_access`` calls inside handler loops.
- Phase 3 AI hardening: structured output retry + optional Pydantic models, Gemini/Azure/Bedrock LLM providers, and `chirp.testing.eval` helpers for mocked LLM/agent regression tests.
- Request-scoped context now flows into **all** streamed renders — `Suspense` deferred blocks, `Stream` generators, and `EventStream` (SSE) generators. `get_request()`, `get_user()` / `current_user()`, `get_csrf_token()`, and `g` now work identically inside any of the three, returning the values that were live in the handler. Previously these raised `LookupError` (or returned `AnonymousUser`) inside an SSE generator because the middleware ContextVars were reset before the stream drained; the shared capture-then-re-establish path now snapshots the request, auth user, CSRF token, and `g` while they are live and re-installs them for the drain (the SSE producer runs in its own task and resets every var in a `finally`, so a stream's identity never bleeds into a later request — safe under free-threading). The zero-`g` hot path allocates nothing (the snapshot reads the raw ContextVar and returns `None` when `g` is untouched). **SSE identity is pinned at connect time:** a user logged out or permission-revoked mid-stream keeps the connect-time identity until they reconnect (per-event revalidation is a deferred follow-up), and the SSE session is a read-only connect-time snapshot, so mutations inside an SSE generator do not persist.
- Session and auth **wiring** is now top-level public, matching the already-stable `login`/`logout`/`get_user`. You can now `from chirp import SessionMiddleware, SessionConfig, get_session, regenerate_session, AuthMiddleware, AuthConfig, current_user` instead of deep-importing `chirp.middleware.sessions` / `chirp.middleware.auth` — closing the gap where `login()` was top-level but the middleware that makes it work was not. All remain lazy (no eager middleware import on `import chirp`). The store backends (`CookieSessionStore`, `RedisSessionStore`, `SessionStore`) stay deep-import as the advanced surface. The one-call `secure_stack` helper is also promoted to the top level (`from chirp import secure_stack`) at the **provisional** tier.
- The stateless bearer path gained optional token revocation via `AuthConfig.token_revocation_store` — a `TokenRevocationStore` Protocol (`is_token_revoked(jti)`, `user_revoked_at(user_id)`) consulted **after** `verify_token` returns a user (token branch only; the try-token-then-session order is unchanged). It mirrors how `AuthConfig.session_version` already gives the session path mass revocation, closing the bearer path's zero-revocation gap. Two axes: a revoked `jti` is rejected, and a per-user cutoff (`iat <= revoked_at`) invalidates every token a user was issued before the cutoff. Because Chirp does not decode tokens itself, a paired `AuthConfig.token_claims` callback `(token) -> {jti, sub, iat}` (sync or async) surfaces the opaque token's claims — keeping `verify_token`'s `(token) -> User` contract intact. Both fields default to `None`, so unset = today's behavior (no bearer-token revocation). A rejected token resolves to an anonymous user and emits a new `auth.token.revoked` security event. Revocation **fails open**: any store/claims error treats the token as not revoked and emits `auth.token.revocation_check_error`, so a revocation-backend blip does not 401 every API client. `TokenRevocationStore` is a module-level name in `chirp.middleware.auth` (mirrors `SessionStore`, not a top-level export); the store owns its own concurrency.
- Three credential primitives in `chirp.security` (`from chirp.security import needs_rehash, verify_and_upgrade, verify_login`). `verify_login(password, phc_hash | None)` kills the user-enumeration timing oracle that the `if user and verify_password(...)` short-circuit leaks: an unknown user (`phc_hash is None`) still runs a full verify against a process-wide decoy hash before returning `False`, so the unknown-user and wrong-password paths take comparable time. The decoy is computed once under a `threading.Lock` (double-checked) so a concurrent first-login burst cannot make N threads each spend ~50-100ms hashing it. `verify_and_upgrade(password, phc_hash)` returns `(ok, new_hash_or_None)` — a freshly computed hash only when the password verified *and* the stored hash is stale, never on a wrong guess (so a failed login can never trigger a database write). `needs_rehash(phc_hash, *, upgrade_algorithm=False)` reports parameter staleness by default (argon2 `check_needs_rehash`; scrypt `n`/`r` below the current pinned cost); the algorithm-upgrade clause — flagging a scrypt hash stale merely because argon2 is now installed — is gated behind `upgrade_algorithm` and off by default to avoid a fleet-wide rehash-write storm when the `auth` extra is installed. `hash_password`/`verify_password` signatures are unchanged. Note: in a mixed-algorithm corpus (legacy scrypt alongside an argon2 default) the decoy's cost differs from a stored scrypt verify, so `verify_login`'s timing equivalence is approximate, not byte-constant — the docstring states this honestly.
- Two new `app.check()` categories harden cookie transport at startup. **`cookie_secure`** flags a session cookie that is not `Secure` while a `SessionMiddleware` is present — store-agnostic (both `CookieSessionStore` and `RedisSessionStore` emit a `Set-Cookie`, so a `Secure`-less session-id cookie is equally hijackable). It is env-aware (silent in development, `WARNING` in staging, `ERROR` in production) so the blessed `SessionConfig(secure="auto")` default passes, and fires an **env-independent `ERROR`** when `samesite="none"` is paired with a non-`Secure` cookie (browsers silently drop such cookies, breaking the session in every environment). **`hsts`** is a `WARNING`-only nudge when a production app with an auth/mutating surface leaves `strict_transport_security` unset — Chirp deliberately does not auto-emit HSTS (an irreversible multi-year browser pin) from a declared-env guess. Both escalate under `chirp check --deploy` and share `resolve_cookie_secure` with the runtime as one source of truth. See `site/content/docs/quality/contracts-debugging/categories.md`.
- Two new env-aware `app.check()` categories guard reading the request user inside an `EventStream` (SSE) generator, shipped alongside the runtime fix that makes `get_user()`/`current_user()`/`get_request()`/`get_csrf_token()`/`g` work inside SSE generators. **`sse_auth_gate`** flags an `EventStream` generator that reads `get_user()`/`current_user()` when no `AuthMiddleware` is registered — the connect-time-captured SSE user would be `AnonymousUser` for the whole stream, so an auth-sensitive feed silently serves the anonymous view. It is env-aware (silent in development, `WARNING` in staging, `ERROR` in production), parallels `auth_middleware`, and escalates under `chirp check --deploy`. **`sse_context`** is a post-fix *semantic nudge* (`WARNING`, never `ERROR`): the pattern now WORKS, but reading the user inside a long-lived SSE loop pins the identity at connect time — a mid-stream logout or permission revoke is not reflected until the client reconnects. Both rules statically resolve the generator in two scopes — an inline nested `async def` inside the handler, and a module-level `async def` passed as `EventStream(gen())` (via the handler `__globals__`) — and silently skip a generator built by any other indirection (a documented blind spot, never a false `ERROR`). Neither fires on the shipped `chat`/`kanban`/`dashboard`/`lucky_cat` SSE examples, whose generators read global state rather than the request user. See `site/content/docs/quality/contracts-debugging/categories.md`.
- Two new env-aware `app.check()` categories harden auth wiring at startup. **`auth_middleware`** flags any route that declares auth — a non-open `RouteMeta.auth` (`"required"` or a permission string) or an `@login_required`/`@requires` handler (detected via the static `_chirp_requires_auth` marker) — when no `AuthMiddleware` is registered. Without it the auth gate's `get_user()` raises `LookupError`, a 500 at request time. It is env-aware (silent in development — the dev 500 surfaces it locally — `WARNING` in staging, `ERROR` in production), names a concrete offending route plus the fix (register `AuthMiddleware` after `SessionMiddleware`), and treats dynamic `meta()` pages as a static blind spot: never a false `ERROR`, just a single `INFO` note when auth wiring cannot be statically verified. **`auth_spec`** catches the silent-403 permission-typo class: a `RouteMeta.auth` that is a case/whitespace variant (`"Required"`, `" required "`, `"None"`, `"Optional"`), a tight misspelling of `"required"` (e.g. `"requied"`), or empty-after-strip silently becomes a *required permission* named that string and 403s forever — env-aware (silent dev / `WARNING` staging / `ERROR` prod). High-signal only: plausible permission names (`"admin"`) are never flagged. Both escalate under `chirp check --deploy`. See `site/content/docs/quality/contracts-debugging/categories.md`.
- `AuthSpec` (`from chirp.pages.types import AuthSpec`) gained a `scopes: tuple[str, ...]` axis for **machine auth** — webhook / cron / provisioning endpoints can now gate on a token-resolved client's *scopes* independently of human permissions. A declarative `RouteMeta.auth = AuthSpec(scopes=("webhook:write",))` (or dict auth `{"scopes": [...], "mode": "any"}`) is enforced by the shared authenticate-or-deny core (`chirp.security.auth_core.enforce_auth`): the resolved client must implement a new `ClientWithScopes` / `MachineClient` Protocol (`scopes: frozenset[str]`, module-level names in `chirp.middleware.auth` mirroring `SessionStore`/`TokenRevocationStore`, **not** top-level exports) and satisfy the scope set under `mode="all"`/`"any"`. The axes are genuinely separate: a token client holding the scope but no permissions passes, and a human user holding the permissions but not the scope fails the scope gate. Scope enforcement is **implicitly off** — a spec with no `scopes` runs no scope step, so existing `verify_token` users are never newly 403'd (no separate enable flag). Scope-name equality is compared in **constant time** via `secrets.compare_digest` (the same primitive `csrf.py`/`passwords.py` use), never `==`. A new `app.register_scope(name, *, description=None)` (setup-only, raises `RuntimeError` after freeze) declares scopes; when a scope registry is declared, the existing `auth_spec` contract check ERRORs (env-aware) on any `AuthSpec.scopes` entry not in it (no new category). A scope denial emits a new `authz.scope.denied` security event (`details={"missing": sorted([...])}`, or `{"reason": "missing_scopes_protocol", "missing": [...]}` when the client lacks the scopes protocol), distinct from `authz.permission.denied` so SIEM can separate machine-scope from human-permission denials; it is parity-locked in `tests/test_auth_parity.py`. Full SCIM provisioning stays out of core. See `src/chirp/security/AGENTS.md` and `site/content/docs/quality/contracts-debugging/categories.md`.
- `RouteMeta.auth` now accepts a structured `AuthSpec` (`from chirp.pages.types import AuthSpec`) in addition to a plain string, giving the **declarative** filesystem-page auth gate full parity with the imperative `@requires` decorator: permission sets with `mode="all"` (subset) or `mode="any"` (intersection), authn-only gating (`AuthSpec(required=True)`), and a named `policy` resolved against an app policy registry. `AuthSpec` is frozen, slotted serializable data — `policy` is a string NAME, never a `Callable`, so route metadata stays static. Plain-string `auth` values are unchanged: `None`/`""`/`"none"`/`"optional"` are open, `"required"` is authn-only, any other string is a single required permission. Both the declarative gate and `@login_required`/`@requires` now share one authenticate-or-deny core (`chirp.security.auth_core.enforce_auth`).
- ``secure_stack(config, *, auth=AuthConfig(...))`` now accepts an optional ``auth`` config and, when given, includes ``AuthMiddleware`` in the returned list — placed after ``SessionMiddleware`` and before ``CSRFMiddleware`` (so a CSRF rejection's audit event already carries the resolved ``user_id``). The whole secure-by-default stack, login auth included, is now one loop: ``for mw in secure_stack(app.config, auth=AuthConfig(load_user=load_user)): app.add_middleware(mw)``. Omitting ``auth`` is unchanged (no auth leg).
- `app.mount(prefix, plugin)` now **quarantines** a plugin whose `register()` raises instead of aborting boot. The exception is caught, the plugin is skipped, and the app keeps starting so one broken plugin cannot take down the whole startup. The quarantine is surfaced two ways so it never hides: a non-fatal WARNING is logged at `mount()` time (naming the plugin, prefix, and original error — so the signal exists even when contract checks are skipped), and `app.check()` reports it as a new ERROR contract category **`plugin_quarantine`** (deploy-blocking under `chirp check --deploy`). Passing a non-plugin object (no callable `register`) stays fail-loud with `ConfigurationError`. Known limitation: a plugin that registers some routes before raising leaves that partial state behind — quarantine does not roll it back. See `site/content/docs/quality/contracts-debugging/categories.md`.

### Changed

- **Furatena docs extraction + patitas 0.4.** Bump the `markdown` extra to `patitas[syntax]>=0.4.0`, tighten markdown sanitization, strip ANSI escape codes from debug error pages, and allow `data:` URI images in the default CSP `img-src`. Simplify docs frontmatter parsing so Bengal site data (collections, glossary, url rewrites) and the new document-catalog protocol docs compile cleanly for the live docs app now living in the Furatena repo.

  Closes #493.
- **Session cookies are now `Secure` by default in production** — `SessionConfig.secure` changes from a static `False` to `"auto"` (the new default). At freeze, `"auto"` resolves to `True` when `AppConfig.env` is `"production"` or `"staging"`, and `False` otherwise (notably local development), so a default-config app served over HTTPS no longer leaks its session cookie over a plaintext path. `env` is the sole posture signal — resolution deliberately ignores `ssl_certfile` and request scheme, so local HTTPS dev keeps `Secure` off and does not log developers out. Opt out explicitly with `SessionConfig(secure=False)`, or force it on with `SessionConfig(secure=True)`; an explicit bool is always honored unchanged. The scaffolds drop the old `secure=not config.debug` band-aid and rely on this default (every scaffold now wires `AppConfig.env` from `CHIRP_ENV`). Breaking only for an app that declares `env="production"` yet is genuinely served over plain HTTP — its session cookie now carries `Secure` and a browser will refuse to send it; set `secure=False` if that is intentional. `chirp security-check` also now treats HSTS as applicable whenever `env="production"` (covering proxy-terminated TLS), not only when `ssl_certfile` is set.
- **Session cookies now sign with HMAC-SHA-256 by default** — `CookieSessionStore` upgrades from itsdangerous' historical HMAC-SHA-1 default to SHA-256. Existing cookies still verify via a SHA-1 fallback signer, so the upgrade does not log current users out. Configurable via the new `SessionConfig.signer_digest` (`"sha256"` | `"sha512"`); an unknown value fails loud with `ConfigurationError` at construction. `CookieSessionStore.load()` now swallows only `itsdangerous.BadData` (tamper/expiry/malformed → fresh empty session) and lets any other exception propagate instead of masking real bugs.
- Phase 2 AI loop: stream_events, native tool-use, AgentRun, ConversationStore, MCP client, `chirp new --ai`, and ollama example refactor.
- Promote the Phase 1 AI/tool surface to stable top-level exports: `LLM`, `AIError`, `ProviderError`, `ProviderNotInstalledError`, `StructuredOutputError`, `ToolDef`, `ToolRegistry`, `ToolEventBus`, and `ToolCallEvent`. Import via `from chirp import LLM, ToolRegistry, ...` — `chirp.ai` re-exports remain for streaming helpers (`stream_to_fragments`, `stream_with_sources`). See `docs/public-api.md`.
- The declarative `RouteMeta.auth` gate and the `@requires` decorator now share one authenticate-or-deny core and emit the same `emit_security_event` shape per outcome, converged on the richer `@requires` payload (the declarative path previously emitted a different `details` shape and no warning log). Permission-denied is `authz.permission.denied` with `details={"missing": sorted([...])}` (a sorted `list`, not a bare string) on both paths; the missing-permissions-protocol case adds `"reason": "missing_permissions_protocol"` alongside `"missing"`; both also emit a `chirp.security` `WARNING`. Downstream SIEM consumers that keyed off the old declarative-path `details` (`{"required": ..., "missing": <string>}`) must read `details["missing"]` as a list.

  Imperative (`@requires`) permission-denied audit events now also carry the request `path` and `method` (they previously did not, because the decorator path passed no `request` to `emit_security_event`). This is a parity-positive payload broadening — both gate paths now emit the same request context on `SecurityEvent`.

  An unresolved/unregistered `AuthSpec.policy` name now **fails loud** — the shared core raises (`LookupError` -> 500) instead of emitting a 403 `authz.policy.denied {reason: "unresolved_policy"}`. There is no `unresolved_policy` event; an unknown policy name is a misconfiguration (also caught at startup by the `auth_spec` contract check), not an auth denial. The only `authz.policy.denied` is a *resolved* policy callable returning falsy.

  The `authz.policy.denied` `details["policy"]` value is the policy IDENTIFIER as referenced — the registered NAME for declarative `AuthSpec(policy="name")` and the function `__name__` for `@requires(policy=fn)` — so the value differs across registration styles by construction. The two paths emit byte-identical payloads only when a policy is registered under a name equal to its callable's `__name__`. The canonical payload table is documented in `src/chirp/security/AGENTS.md` and the parity (unauthenticated, permission-denied, missing-protocol, and matched policy-denied) is locked by `tests/test_auth_parity.py::TestAuditEventParity`.
- `AuthRateLimitMiddleware` is now a general-purpose keyed rate limiter. `AuthRateLimitConfig` gains three fields: **`key_fn`** (`Callable[[Request], str | None]`) computes the bucket key for a request — return a non-empty `str` to key on a per-user / per-resource / per-tenant identity, or `None` to skip rate-limiting that request entirely (an explicit per-request opt-out); the default (`None`) keeps the fail-closed `request.trusted_client_ip` keying. **`error_template`** / **`error_block`** opt into a self-contained HTML `429` body: when set and the over-limit request is htmx, the middleware renders the named block (or the whole template, with `retry_after` in context) to the `429` `Response` itself — a missing block is fail-loud (`BlockNotFoundError`); non-htmx and unconfigured over-limit responses keep the plain-text `Too Many Requests` body. An empty `paths=()` now targets **every** matching-method route, so the limiter can cover an arbitrary route/group rather than only the auth path prefix. The pluggable-backend Protocol **`RateLimitBackend`** and the **`redis_rate_limit_backend`** factory are now exported from `chirp.middleware`. `key_fn` is authz-adjacent: derive the key from a server-side identity, never from a client-controlled value a caller could rotate to dodge its own bucket.

### Fixed

- Fail closed when verifying a corrupt password hash. ``verify_password`` (and the underlying argon2/scrypt helpers) now returns ``False`` for a malformed or truncated hash string instead of raising. The argon2 path previously caught only ``VerificationError``, so a corrupt argon2 hash (``InvalidHashError``, which derives from ``ValueError`` — not from ``Argon2Error``) bubbled up as a 500; it now catches both ``Argon2Error`` and ``InvalidHashError``. The scrypt path is hardened the same way for inputs that produced an invalid derived-key length. The argon2id cost factors (RFC 9106 §4 second recommended option — t=3, m=64 MiB, p=4) are now pinned explicitly and match argon2-cffi's ``PasswordHasher()`` defaults, so existing hashes keep verifying and are not flagged stale.
- Make long-lived signal/SSE streams resilient to source failures and client disconnects. A `@app.signal` source that raises is now restarted with bounded backoff (capped, so a deterministically-failing source is logged-and-dropped rather than hot-looping or silently killing the binding for the life of the connection) and its failure log carries the `audience`. Mid-stream client disconnects (`ConnectionResetError`/`BrokenPipeError`) are classified by the new `is_client_disconnect()` helper and logged at DEBUG instead of surfacing as a 500-class `Server error`, so a browser tab closing no longer trips error-rate alerting. Closes #355.

### Security

- `Request.trusted_client_ip` — a new fail-closed accessor that returns the trusted-proxy-corrected client IP (`client[0]`, or `"unknown"` when the scope has no client) and never raises. It deliberately ignores raw, client-spoofable `X-Forwarded-For`. `AuthRateLimitMiddleware` now keys off it and no longer does its own first-comma `X-Forwarded-For` split, so a rotating spoofed `X-Forwarded-For` can no longer evade auth rate limits. `AuthRateLimitConfig.key_header`, when set, now names a TRUSTED server-set identity header consumed verbatim (no comma split), not an XFF override.


## [0.8.1] — 2026-06-16

### Added

- ✨ **`signal_attrs()` template global — bind a signal on an existing element.**
  A third signal binding helper alongside `signal()` / `signal_block()`: it emits the
  binding **attributes only** (`sse-swap="name" hx-target="this"`) for placement
  inside an element you already have — `<section class="board" {{ signal_attrs('stats') }}>` —
  so a layout's own CSS-grid / flex container (or a `<ul>`) becomes a live sink
  without an injected `<span>`/`<div>` wrapper breaking its layout. Unlike a
  hand-written `sse-swap` attribute, the `signal_attrs('x')` call is recorded for
  topic scoping and recognised by the `signal_dead_binding` contract by its call-site,
  so the binding is validated even though the `sse-swap` is produced at render time.
- 🔐 **Lucky Cat — authentication showcase.** The flagship ChirpUI example now
  demonstrates Chirp's auth subsystem end to end, exercising all three gating
  levels rather than a blanket lockdown:

    **Full-page gating** — `@login_required` on the account section (`/portfolio`,
    `/activity`, `/trade`, `/settings`, `/markets/favorites`); an anonymous hit redirects to
    `/login?next=…`. **Component gating** — `current_user()` conditional chrome: the
    topbar swaps between a "Sign in" link and the user menu + Sign-out (and reveals
    the $MEOW balance, the notifications bell, and the Deposit action), and the
    watchlist star on the *public* markets grid becomes a "sign in to star" link.
    **Action gating** — `@login_required` on the mutation routes (deposit, place /
    cancel order, convert, star toggle, notifications-read) as the security backstop.

    The sign-in flow is return-type-driven: `ValidationError` re-renders the login
    form in place (422) on bad credentials, and a clean sign-in returns `FormAction`
    (HX-Redirect for htmx → a full reload) so the persistent topbar repaints its
    auth state. Public market data (the
    markets grid and a market's detail page) stays browsable without an account.
    Built on `AuthMiddleware` + `login()`/`logout()` + a single in-memory demo
    account (`users.py`), with passwords hashed via `chirp.security.passwords`
    (stdlib scrypt fallback — no extra dependency).
- 🔥 **Lucky Cat — Trending destination (`/markets/trending`).** A new fixed Markets
  destination: a movers leaderboard with a segmented Gainers / Losers / Volume
  control that swaps a `#movers-region` over htmx (snapshot-per-swap, no live
  re-rank). It is backed by the shared `ranking` / `research` query seam, so its
  numbers and ordering match the rest of the Markets surfaces. The segment toggles
  self-override the boosted shell's inherited outlet (`hx-target` / `hx-select` →
  `#movers-region`) and `page.py` re-emits that wrapper — the canonical
  boosted-shell local-swap pattern (footgun #2).
- 🔬 **Lucky Cat — Research destination (`/markets/research`).** A new fixed Markets
  destination and the scalable power surface for a 500+ coin catalog: substring
  search (sharing the same `search.matches` matcher as the Cmd-K palette), facet
  filters (sector + price / 24h-change / volume bands), sortable column headers,
  **server-side pagination**, and a lightweight server-rendered compare tray. It is
  URL-param-driven (`?q=&sort=&dir=&page=&sector=` + band keys + `cmp`), so every
  control is a bookmarkable querystring and the whole surface is back-button-correct;
  each control's `hx-get` URL is precomputed in `page.py` (the `research_url` helper)
  and the filter → stable-sort → slice runs entirely server-side via the shared
  `research.query_catalog` seam, so it renders only one page of rows regardless of
  catalog size and its numbers / ordering match the rest of the Markets surfaces.
  Every search / sort / filter / paginate / compare control self-overrides the
  boosted shell's inherited outlet (`hx-target` / `hx-select` → `#research-results`)
  and `page.py` re-emits that wrapper — the canonical boosted-shell local-swap
  pattern (footgun #2).

### Changed

- ### Testing

  - Add ``chirp.testing`` link-integrity helpers (#234): ``same_origin_paths``, ``crawl_links``, and ``assert_link_integrity`` for deterministic href crawls, plus opt-in Playwright shell smoke helpers.

  Closes #234.

  ([#234](https://github.com/lbliii/chirp/issues/234))
- ### Developer Experience

  - `AppConfig.from_env()` now accepts keyword overrides (e.g. `template_dir`, `worker_mode`) applied after env loading, so Railway-style apps no longer need `dataclasses.replace(AppConfig.from_env(), ...)`.
  - `app.check()` dead-template detection now scans route-handler modules for `Fragment(...)`/`Template(...)` string literals and module-level `*.html` constants, so templates referenced only from Python helpers are no longer false-positive orphans.

  Closes #237.

  ([#237](https://github.com/lbliii/chirp/issues/237))
- ### Examples

  - Lucky Cat Dockerfile now installs `bengal-chirp[ui,sessions,forms]` from PyPI (>=0.8.0) instead of git@main; the deploy workflow no longer triggers on `src/chirp/**` changes.

  Closes #246.

  ([#246](https://github.com/lbliii/chirp/issues/246))
- ### Documentation

  - Document asyncpg's experimental free-threading status and its relationship to Chirp's `data-pg` extra on Python 3.14t, with links to the pelt saga.

  Closes #263.

  ([#263](https://github.com/lbliii/chirp/issues/263))
- ### Examples

  - Lucky Cat acceptance tests (#285) prove per-session isolation for wallet balances, trade positions, and notification lists across concurrent browser sessions.

  Closes #285.

  ([#285](https://github.com/lbliii/chirp/issues/285))
- ### Examples

  - Lucky Cat exposes the scaling seam (#295): a ``SignalBackplane`` protocol, in-process default, and stubbed ``RedisBackplane`` with wiring notes; ``DESIGN.md`` reframes ``workers=1`` as the single-process default.

  Closes #295.

  ([#295](https://github.com/lbliii/chirp/issues/295))
- ### Examples

  - Lucky Cat market buys now have acceptance tests (#296) proving a fill consumes top-of-book depth and appends to the trade tape via both the store and HTTP POST paths.

  Closes #296.

  ([#296](https://github.com/lbliii/chirp/issues/296))
- ### Contracts

  - Signal dead-binding checks now validate hand-written `sse-swap` on pages composed under a `signal_connect()` layout (with an INFO nudge to prefer `signal_attrs()`), while pages that open their own `sse_scope()` stream are excluded.

  Closes #316.

  ([#316](https://github.com/lbliii/chirp/issues/316))
- **Suspense docs** — CLAUDE.md and AGENTS.md now recommend `{% if key is deferred %}` instead of the incorrect `is not none` idiom for deferred keys (#236).
- Bumped the `chirp-ui` floor to `>=0.10.0` across the `ui` extra, dev group, and the `chirp new` scaffold so generated projects match the framework's pinned component-library version.
- Rewrote Lucky Cat inline docs for newcomers: template construct legend, minimal Suspense first, stripped issue-number noise from reader-facing comments, and removed redundant auth/CSRF capture now that the framework preserves streaming context.
- ⚡ **Signals skip redundant emits.** A coalescing signal (`coalesce=True`, the
  default) now skips the wire event **and** the derived cascade when its new value
  equals the current one — a pure `render` maps equal values to equal payloads, so
  the swap would be byte-identical. Derived signals dedup the same way: a derived
  whose projection is unchanged (even when its source value changed) no longer
  re-emits or propagates. This makes the *compute-once / broadcast-many* dashboard
  pattern cheap — only regions that actually changed hit the wire. Append-style /
  drop-sensitive topics opt out with `coalesce=False` (every emit fires, even a
  repeat value).
- ⭐ **Lucky Cat — Markets rail rework + Favorites move (`/watchlist` → `/markets/favorites`).**
  The Markets contextual rail is now **four fixed destinations** — Home, Favorites,
  Trending, Research — instead of an O(N) one-row-per-market list (the full catalog
  lives in Research). On a coin-detail route the current market is pinned in the
  rail, and the dead Overview / Order-book / Trades / Info jump anchors are gone.
  The starred-markets view moved from `/watchlist` to `/markets/favorites` (one of
  the fixed destinations); `/watchlist` now answers a **308 permanent redirect** so
  existing bookmarks keep working, and a `RouteState` reserved-segment guard keeps
  `/markets/{favorites,trending,research}` from being mistaken for a coin symbol.
- 🐱 **Lucky Cat — Markets Home is now a curated lobby (`/markets`, with `/` as an
  alias).** The old full markets grid landing is retired for a bounded lobby (~9
  cards): a stat strip (`ranking.market_stats`), a top-movers preview
  (`ranking.top_gainers/losers/volume`, a few each, as links into Trending), a
  watchlist preview, a featured market, and a CTA into Research — the full 500+ coin
  catalog now lives only in Research. `/` is an **alias** (no redirect) rendering the
  SAME `markets/page.html` from one shared `lobby.lobby_context`, so the two routes
  can never drift. The card-bearing regions (featured + watchlist preview) are
  de-duped at render — the featured symbol is dropped from the watchlist preview so
  `#luckycat-card-{symbol}` / `#watchlist-star-{symbol}` never duplicate (the
  no-duplicate-id invariant + the `/watchlist/toggle` unstar-prune target). Boosted
  in-shell links carry the full `shell_outlet_attrs()` outlet contract.
- 🐱 **Lucky Cat — the Markets lobby is now fully reactive.** The whole board updates
  live over the single `/_chirp/live` connection: the stat strip (24h volume /
  advancers / decliners) ticks with directional flash, the movers grid (Gainers /
  Losers / Volume) re-ranks live, and the featured slot is a bespoke spotlight whose
  price + sparkline update and that re-ranks to follow the current top gainer. It is
  the canonical *live board* recipe — one source signal (`lobby_snapshot`) samples
  the feed on a human cadence and emits a self-contained snapshot, and three
  `@app.derived` projections (`market_stats` / `movers` / `featured`) re-render their
  regions in lockstep, bound with the new `signal_attrs()` on the existing grid
  containers. The featured spotlight no longer reuses the `market_card`
  `#luckycat-card` / `#watchlist-star` ids, so it can change symbol live without
  colliding with the (static, per-session) watchlist preview.

### Fixed

- `app.check()` no longer emits a false-positive `oob_target` warning for chirp-ui's own OOB helper macros (e.g. `context_rail_oob` targeting `chirpui-context-rail`). The OOB-target check now skips vendored `chirpui/` templates, symmetric with id-collection, since chirp-ui owns its internal OOB-target consistency. ([#307](https://github.com/lbliii/chirp/issues/307))
- **Contract diagnostics** — `select_inheritance` now recommends overriding inherited `hx-select` with an explicit selector or `hx-select="unset"` instead of `hx-disinherit` (#235). Added `duplicate_id` and `oob_fragment_orphan` startup checks for repeated static element ids and dead-wired OOB fragment blocks (#238). DevTools empty `hx-select` warnings now walk from the request trigger, not the swap target (#248).
- Bump ``asyncpg`` to ``>=0.31`` for free-threaded safety and add a 3.14t CI gate that imports the Postgres backend with ``PYTHONWARNINGS=error``.

  Closes #261, #262.
- Fix htmx ``hx_redirect()`` negotiation, Suspense auth/CSRF stream context, and ``RouteMeta.auth`` enforcement.

  Closes #272, #273, #274.


## [0.8.0] — 2026-06-15

### Added

- **AI-buildable positioning.** The comparison docs now explain how Chirp is buildable by construction: `app.check()` contracts are independent declarative invariants that name their own fix (stable category as the CI handle, message as the concrete fix target), so an agent can build correct Chirp apps from the public-API surface plus contract errors instead of relying on a large community corpus. Documented Chirp's place *alongside* platforms like Django (keep its admin/ORM/auth; let Chirp own the hypermedia UI surface) and called out the five static accessibility checks (`a11y_interactive`, `a11y_label`, `a11y_alt`, `a11y_heading`, `a11y_landmark`) that validate a11y affordances at startup rather than claiming support. The README feature list gains a matching contract-checked, AI-buildable correctness note.
- **Added `signal()` — server-owned reactive values over a single SSE connection.** Declare a live value with `@app.signal(name, ...)`, a computed one with `@app.derived(name, on=(...))`, push updates with `app.emit(name, value)`, and bind it anywhere in a template with `{{ signal('name') }}` / `{{ signal_block('name') }}` under one `{{ signal_connect() }}` wrapper. A single named value fans out to *every* binding — declare once, bind many — over one shared `/_chirp/live` stream, so an SSE-heavy page holds **one** connection instead of N (the topbar balance and a modal can update together from one `app.emit`). `app.check()` validates bindings against producers (`signal_dead_binding` → ERROR, `signal_orphan` → INFO). A `derived` must be a pure function of its input signals (never read process-local state) so it stays correct across workers. Built on the existing realtime bus + htmx `sse-swap`; the single-node primitive ships now, with a pluggable multi-worker `SignalBus` backplane designed in `plan/drafted/rfc-live-sse-topics.md` (§12).
- **Bounded nested compiler** (#167): a `@shape`-decorated row model can now declare child Shapes with `nested(Child, on="parent_fk", key="parent_pk")`, and `Shape.fetch`/`Shape.fetch_one` assemble the tree behind the `Database` seam in a bounded number of queries — exactly `1 + (number of declared child levels)`, independent of the parent row count `N`. Each child level runs ONE batched `WHERE {on} IN (...)` query (never one query per parent row), groups children by their join column, and attaches them to each frozen parent via `dataclasses.replace`. `nested()` returns a `dataclasses.field(default=())` so a plain parent row maps cleanly (the absent nested column is filled by the empty-tuple default), and `@shape` fails loud with `ShapeError` if a scalar field is declared after a `nested()` field (the field-ordering constraint). A nested child that is unexpressible by the batcher — opaque SQL (`SELECT *`/CTE/UNION), a missing join column, or a missing parent key — fails loud via `Shape.validate(cls)` at startup rather than silently leaking per-row queries at runtime. `NestedShape` and `nested` are exported from `chirp.data`.
- **CLI** - Added `chirp --version` (and `-V`), which prints the installed chirp, kida, pounce, and Python versions on one line — making a stale install obvious before it errors at runtime.
- **Canonical Non-Goals doc.** Added `docs/about/non-goals` as the single authoritative list of the bright lines Chirp's core deliberately won't cross — no stateful ORM, no in-core admin/CRUD generator, no in-core email, no background-jobs scheduler, no WebSocket return type (SSE over WebSockets, always), no WSGI / no Python floor below 3.14, no general HTTP rate limiting in core, no in-core telemetry/APM, and no ecosystem absorption — each paired with the honest alternative. Leads with the identity claim that Chirp holds zero per-client server view state. The Philosophy "What Chirp Is Not" section and the PRD "Out of Scope" section now link to it instead of forking the list.
- **Contract diagnostics** - Added a `suspense_defer` startup contract: `app.check()` now warns when a template self-declares a Suspense-deferred key (via `is deferred` or `__chirp_defer_pending__`) that no block depends on, so auto-discovery would find nothing to re-render. The message recommends moving the key into a `{% block %}` or passing `Suspense(..., defer_blocks=(...))`. Detection is scoped to self-declaring templates (no false positives on sync-only Suspense), exempts handlers that already use `defer_blocks=`, and is overridable via `app.override_contract_severity("suspense_defer", Severity.ERROR)`.
- **Contract diagnostics** - Added a source-backed contract category reference and tightened reactive stream guidance for `ConnectionInfo`, presence, audience scopes, changed-path context builders, and reactive `app.check()` metadata.
- **Data shapes** - Added `@shape` and `Shape` to `chirp.data`: decorate a frozen, slotted dataclass with `@shape("SELECT ...")` to declare its SQL co-located with the row model, then run it behind the `Database` facade via `await Shape.fetch(BoardView, db, id=42)` (plus `Shape.fetch_one` and `Shape.stream`). The author writes `:name` placeholders; Chirp resolves the driver dialect (`?` for SQLite, `$N` for PostgreSQL) in one place and never concatenates parameters into the SQL text. Decorated shapes are auto-registered in a thread-safe, read-only registry (`register_shape` / `shape_registry`) for drift detection; registering a different class under an existing name fails loud with `ShapeError`, which also fires on a non-frozen / non-slotted / non-dataclass target. `@shape`, `Shape`, `ShapeError`, `register_shape`, and `shape_registry` are exported from `chirp.data`.
- **Deploy-preflight contract checks.** `app.check()` now ERRORs on `debug=True` in production (`deploy_debug`) and on a `metrics_path` that collides with an application route (`deploy_metrics`), and WARNs when a Sentry DSN is set with `sentry_traces_sample_rate=0` (`deploy_sentry`). Check rules only — no deploy automation.
- **Documented the SQLite concurrency ceiling.** The database guide now states plainly that Chirp's current SQLite "pool" is a single shared connection serialized behind one async lock, so every read, write, and `transaction()` is serialized app-wide — and under Python 3.14 free-threading a SQLite transaction serializes database work for the whole app. SQLite remains the default for development, single-writer, and small apps; write-heavy concurrency should use PostgreSQL, whose `asyncpg` pool runs transactions in parallel.
- **Documented the `signal()` primitive.** Added a narrative guide for server-owned reactive values — what a signal is (declare once, bind many over one SSE connection), when to use it vs `EventStream` / `Suspense` / `Stream`, the three pieces (`@app.signal` / `@app.derived` / `app.emit` and the `signal()` / `signal_block()` / `signal_connect()` bindings), the pure-derived rule, a worked balance/net-worth example, and a plainly-stated single-process production constraint (run `workers=1` / `worker_mode="async"`; multi-worker realtime needs a shared bus backplane, forward-referenced to the live-SSE-topics RFC §12). Site guide at `site/content/docs/build-apps/streaming-updates/signals.md`, cross-linked from the streaming-updates index; the `docs/realtime-production.md` signal section is filled with the same production rules. Documentation only — no behavior change.
- **Documented the boundary contract for future account-recovery flows.** The auth hardening guide now records that any future password-reset or email-verification flow must carry state in stateless signed tokens (`itsdangerous`, like sessions) or an app-provided token store — never a framework-owned per-user token table — and must render a Kida body handed to a bring-your-own mailer callback shaped like `AuthConfig.load_user`, never a bundled mailer or SMTP dependency. Cross-links the no-ORM and no-email Non-Goals.
- **Documented the five static accessibility contract checks.** The accessibility guide now enumerates the template checks that run inside `app.check()` — `a11y_interactive`, `a11y_label`, `a11y_alt`, `a11y_heading`, and `a11y_landmark` (all `WARNING`) — what each catches, and that they run at startup and in CI. It also shows how to adopt a strict accessibility posture with the existing severity-override mechanism, e.g. `app.override_contract_severity("a11y_label", Severity.ERROR)`.
- **Examples** — Added `examples/standalone/shapes_workspaces`, a multi-tenant project tracker that showcases the `chirp.data` Shapes data layer end-to-end: a startup-verified SQL→render contract (`shapecheck`), tenant `scope=` isolation proven at the page *and* data layer (no hand-written `WHERE workspace_id = ...`), and a bounded `nested()`/`@composite` dashboard whose query count stays constant as rows grow (no N+1). Its tests assert all three guarantees, including a query-count proof and a cross-tenant 404. The example-loading test harness (`examples/conftest.py`, `test_examples_contract_clean.py`, `test_examples_smoke.py`) now snapshots and restores the process-global `@shape` registry around each load, so an `@shape` app reloaded more than once per process no longer collides on duplicate Shape names.
- **HTTP 103 Early Hints via the `Link`/preload header convention.** Set an asset-preload-class `Link` header on a response — `rel=preload`, `modulepreload`, `preconnect`, `dns-prefetch`, `prefetch`, or `prerender` — and Chirp's sender now emits a preliminary `103 Early Hints` frame ([RFC 8297](https://www.rfc-editor.org/rfc/rfc8297)) carrying those headers before the final response, so the browser can start preloading/preconnecting while a slow-first-byte page (`Suspense`, `Stream`) is still rendering. The same `Link` headers stay on the final response. There is no new return type or config flag — the lever is the header convention. pounce 0.8.0 serializes the 103 over HTTP/1.1, HTTP/2, and HTTP/3; a sync-fast-path request that emits a 103 is transparently re-run on the async worker. Navigational/metadata `Link` relations (`canonical`, `stylesheet`, …) are not promoted. See [Early Hints](https://chirp.dev/docs/build-apps/request-pipeline/early-hints/).
- **Missing-translation-key contract (`i18n_missing_key`).** When i18n is enabled and catalogs are present, `app.check()` WARNs on `t("…")` keys referenced in templates but missing from the locale JSON catalogs — a fail-loud key-coverage guarantee. ICU pluralization/formatting remains deferred to babel-alongside.
- **New `FileResponse` type with conditional-GET and Range support.** `chirp.FileResponse` is a frozen dataclass that serves a file from disk through a dedicated bytes-capable ASGI sender. Static responses now emit `ETag`, `Last-Modified` and `Accept-Ranges: bytes`, answer `If-None-Match` / `If-Modified-Since` with `304 Not Modified`, and honour a single byte `Range` with `206 Partial Content` (`416` when unsatisfiable). `ETag` is derived from file size + mtime — stable for a file on disk, not a content hash, consistent with Chirp shipping no asset pipeline. `StreamingResponse` stays str-only for HTML/SSE; binary bodies go through `FileResponse` exclusively. ([#178](https://github.com/lbliii/chirp/issues/178))
- **No-JS floor contract (`nojs_floor`).** `app.check()` flags (INFO) mutating routes whose only success path is an htmx `Fragment`/`OOB` with no `FormAction`/`Redirect`/`Page` fallback — such a route has no success path with JavaScript disabled. INFO by default because htmx-only mutation is a legitimate choice; promote it with `override_contract_severity("nojs_floor", Severity.ERROR)` to enforce the progressive-enhancement floor.
- **Page-composite + repository seam** (#170/#171): a page can now declare its data ONCE with `@composite()` over a frozen, slotted dataclass whose fields are `@shape`-decorated member types — a single `@shape` class (single-object) or a `tuple[Shape, ...]` (a list). `await Composite.load(BoardPage, db, **params)` runs the batched query set across the member Shapes behind the `Database` facade (reusing the bounded nested compiler for nested members), coalesces the shared tenant `scope` plus params — threading `:scope` to every member that declares a matching `scope=` so the page scopes once and members inherit it — and returns one frozen instance. A composite field that is not a Shape member fails loud with `ShapeError` at decoration. The `shapecheck` contract resolves a block bound to `page.field` to that composite member's Shape, so the per-block read-subset check runs against the composite member's provided fields (columns + declared computed) rather than one query per block. The repository seam is structural: SQL lives only on the `@shape`/`@composite` declarations (co-located with the row model and block) and materializes solely behind `Shape.fetch` / `Composite.load`; no public render-time return type accepts a raw SQL string, and the frozen result — never SQL — is what reaches the template. `Composite` and `composite` are exported from `chirp.data`.
- **Secure-by-default scaffolds.** `chirp new --minimal` and `chirp new --shell` now wire the full Session/CSRF/SecurityHeaders middleware stack (with `CHIRP_SECRET_KEY` handling and the production-secret guard), mirroring the default `chirp new` scaffold. Generated apps read `CHIRP_ENV` and `CHIRP_DEBUG`, so a generated minimal/shell app can run in production (debug defaults off outside development) and is exercised by the env-aware `security_stack` contract — it passes in production out of the box, so adding a mutating route never silently ships unprotected mutations. Because every scaffold now wires `SessionMiddleware` (whose default cookie store signs with `itsdangerous`), generated `pyproject.toml` moves `itsdangerous>=2.2.0` from the `auth` extra into base dependencies.
- **Security-stack contract check.** `app.check()` now flags apps with mutating routes that are missing the secure-by-default stack (`security_stack`). A route is mutating when it accepts POST/PUT/PATCH/DELETE **or** is a filesystem page that ships `_actions.py` form actions — including a page whose `page.py` declares only `get()` but mutates state via POST-to-self on the `_action` field. Missing `CSRFMiddleware` or `SessionMiddleware` is an ERROR in production, a WARNING in staging, and silent in development; missing `SecurityHeadersMiddleware` is always a WARNING. No middleware is force-injected — the lever is the contract plus scaffold defaults. This category is the canonical owner of the "mutating route" definition referenced by the forms/auth contracts.
- **Shapes — the verified SQL→render data contract.** Chirp's answer to the ORM, without becoming one: each hypermedia block declares the exact data `Shape` it needs as a frozen, slotted dataclass with co-located SQL; the shape runs behind the `Database` facade producing frozen instances; and `app.check()`'s new `shapecheck` category proves at startup that the block reads only fields the query provides. This release lands the full set — `@shape` + `Shape` (fetch/fetch_one/stream), declared `computed=` members, `nested(...)` batched child shapes (a bounded `1 + child-levels` query count independent of row count, fail-loud when un-expressible), per-`@shape`/`@composite` tenant `scope=` injection, page-level `@composite` aggregation behind the repository seam, the `shapecheck` contract (registry-drift / under-fetch / over-fetch + the escape-hatch model), and the `chirp shapes-codegen` CLI for adopting Shapes view-by-view with a `--audit` drift report. The honest marquee is the **field-level + registry-drift startup contract** (the thing no ORM, SQL tool, or GraphQL layer can offer, because only Chirp owns both the query and the template) — *not* "N+1 impossible." Field-level verification is conservative single-object analysis with documented escape hatches; see the [Shapes guide](/docs/build-apps/forms-data/shapes/) for exactly when the check stays silent and how to tune severity. RFC: `plan/completed/rfc-shapes.md`.
- **Tenant-scope injection** (#169): a `@shape` can declare a multi-tenant scope key with `@shape("SELECT ...", scope="community_id")`. The compiler then **structurally injects** the scope predicate (`community_id = :scope`) into every compiled statement — the parent SELECT and every batched child `IN`-list query — threading the `:scope` value from the `Shape.fetch(...)` keyword arguments. The guarantee is unconditional and delivered by asserting on the compiler's *output*, not by a flaky WHERE-column scanner: `Shape.validate(cls)` (run during the `shapecheck` startup pass) confirms the injected statements carry the predicate, and a scoped Shape whose SQL is opaque/un-injectable (CTE / UNION / `SELECT *` / no analyzable FROM) fails loud — `ShapeError` from the compiler, and a `shapecheck` ERROR from `app.check()` — because the predicate cannot be safely added and the query would otherwise silently read across tenants. There is no new `AppConfig` field; scope is declared per-`@shape`.
- **Two new `app.check()` contracts (WARNING).** `macro_css` (#148) warns when a template imports core chirp macros (`chirp/alpine.html` / `chirp/forms.html`) or emits their dangling classes (`chirp-dropdown`, `chirp-modal`, `field--error`, …) while chirp-ui is not active — those classes have no backing stylesheet, so components render unstyled with no error. `htmx_provisioned` (#185) warns when a template emits `hx-*`/`sse-*` attributes but htmx is not provisioned via `AppConfig(htmx=True)` nor an htmx `<script>` in the layout chain, so the attributes are inert. Both ship at `WARNING` (non-build-breaking) and name their own fix; promote to ERROR with `app.override_contract_severity(...)` in CI.
- **Unified bind + validate from one dataclass schema.** `form_or_errors()` now runs `chirp.validation` rules attached to dataclass fields via `Annotated` — e.g. `title: Annotated[str, required, max_length(100)]` — in the same pass as binding, with no separate `validate()` call and no `Form`/`ModelForm` class. Rule errors and binding errors merge per field (message lists concatenated), `context["form"]` re-populates the raw submitted values, and `Optional`/union nesting (`Annotated[str | None, required]`, `Optional[Annotated[str, required]]`) is unwrapped to find the rules. Falsy-but-valid values stay valid (`"0"` satisfies `required`; an omitted `list[str]` binds to `[]`). A plain dataclass with no `Annotated` rules behaves exactly as before — binding only. `form_from()` is unchanged.
- **`AppConfig(htmx=...)` opt-in htmx injection.** New `htmx: bool = False` and `htmx_version: str = "2.0.4"` config fields, symmetric with `alpine`/`alpine_version`. When `htmx=True`, Chirp injects the htmx core `<script>` before `</body>` (jsDelivr explicit `/dist/htmx.min.js` path, carrying the live per-request CSP nonce) on both buffered full-page and `StreamingResponse`/Suspense paths, and dedups on `data-chirp="htmx"` so a template that already ships its own htmx tag is left untouched. Default off — never global default-on. `use_chirp_ui()` does **not** auto-enable it (the chirp-ui layouts already ship their own htmx tags); those tags now carry `data-chirp="htmx"` so the dedup skips re-adding the core script if an app opts in anyway. ([#184](https://github.com/lbliii/chirp/issues/184))
- **`AppConfig(rate_limit_max_tracked_ips=...)`, `AppConfig(trusted_proxies=...)`, and `AppConfig(forwarded_for_trusted_hops=...)`** — production-server knobs threaded through to pounce 0.8.0's `ServerConfig`. `rate_limit_max_tracked_ips` (default `100_000`) bounds the per-IP rate limiter's tracked-IP map under a wide or spoofed source-IP fan-out (LRU eviction past the cap). `trusted_proxies` (default `()`, env `CHIRP_TRUSTED_PROXIES`) is the reverse-proxy peer IP/hostname allowlist that gates whether `X-Forwarded-For` is honored — it maps to pounce `ServerConfig.trusted_hosts`, so an empty value means `X-Forwarded-For` is ignored entirely and the request client IP is the raw socket peer. `forwarded_for_trusted_hops` (default `1`, env `CHIRP_FORWARDED_FOR_TRUSTED_HOPS`) controls how many trailing `X-Forwarded-For` hops are trusted when deriving the client IP; it is only honored when the direct peer is a trusted proxy and must be `>= 1` — `AppConfig` now fails fast with `ConfigurationError` at construction (instead of only at pounce launch) if it is `< 1`. To ignore `X-Forwarded-For`, leave `trusted_proxies` empty rather than setting the hop count to `0`. A new `trusted_proxies` contract check emits a `WARNING` when `trusted_proxies` contains `"*"` outside development, since `"*"` trusts every direct peer's forwarded headers (client-IP spoofing / rate-limit bypass risk).
- **`FileResponse` now honours `If-Range` on Range requests (RFC 9110 §13.1.5).** When a `Range` request also carries `If-Range`, the partial `206` is served only if the supplied validator still matches the current representation — a strong-compared `ETag`, or a `Last-Modified` HTTP-date equal to the current one. If the validator is stale (the file changed), the `Range` is ignored and the full `200` representation is returned instead of a `206` slice of mismatched bytes. This is the standard mechanism that lets clients safely resume an interrupted download without stitching together two different versions of a file.
- **`chirp check --deploy` runs a production-posture deploy preflight.** The new `--deploy` flag (and `app.check(deploy=True)`) evaluates the env-aware safety rules — `secret_key`, `allowed_hosts`, `security_stack`, `csp_nonce`, `deploy_debug`, `deploy_metrics`, `deploy_sentry` — with `env="production"` severity and treats warnings as errors, answering "would this app pass `app.check()` in production?" without leaving development. It is tighten-only (only raises severities, so a genuinely deploy-ready app still passes) and never mutates the running app: it builds a throwaway production-posture *view* of the config rather than reconfiguring the app. `--deploy` implies `--warnings-as-errors`. Use it as a CI deploy gate.
- Added the `examples/standalone/htmx_managed/` example — a runnable demonstration of Mode A htmx provisioning (`AppConfig(htmx=True)`): a template that ships `hx-*` attributes and no htmx `<script>`, with Chirp injecting the runtime so `app.check()` stays clean and the swap works.
- `chirp shapes-codegen` (#172): a codegen + audit CLI for the Shapes workflow. Run `chirp shapes-codegen [PATH]` to scan a directory or file for frozen dataclasses sitting near an explicit named-column `SELECT` literal and print a suggested `@shape("SELECT ...")` decorator above each match — incremental and view-by-view, pairing each dataclass to the `SELECT` whose output columns are a subset of its fields. The scan is a safe dry-run by default (`--dry-run`): nothing on disk is modified, and only `SELECT`s the conservative parser can read are suggested, so every emitted decorator is one `shapecheck` can later verify. Run `chirp shapes-codegen <app:import> --audit` for a day-one drift report: it loads the app's `surface_contracts` registry (set via `app.set_contract_check_data("surface_contracts", {...})`) and reports every surface name with no backing Shape — reusing the exact registry-drift logic (and closest-match suggestion) that `app.check()`'s `shapecheck` runs — exiting non-zero on drift for CI and 0 when clean.
- `shapecheck` contract category (#166/#168/#173): `app.check()` now verifies the render side of `@shape`-decorated row models. **Registry drift** (ERROR, the headline): a surface-contract name that resolves to no registered Shape is flagged with a closest-match suggestion — and this runs even with no contract data, via the auto `shape_registry()`. **Under-fetch** (ERROR): a block reading `shapevar.field` for a field the bound Shape neither fetched (SELECT column) nor declared (`computed=`) is caught before it silently renders as `None`. **Over-fetch** (WARNING, promotable): a fetched column no bound block reads. A `PASS shapecheck: N verified` INFO line surfaces verified bindings. The check is conservative — single-object access only, with documented escape hatches for globals, block-local bindings, loop-collapsed reads, macro args, opaque shapes, and **derived accessors** (a `@property`/method on the Shape dataclass such as `{{ person.full_name }}` resolves at runtime and is never flagged) — and never double-fires with the `data` category. Override via `app.override_contract_severity("shapecheck", ...)`.

### Changed

- **Recorded the ICU-defer scope decision for i18n.** Chirp keeps JSON key catalogs and the `i18n_missing_key` contract check in core, and defers ICU pluralization, number, date, and currency formatting to `babel` used alongside Chirp. Core ships no gettext, no `.po`/`.mo` compilation, and no ICU engine; `formatting.py` provides only minimal locale-aware number/date helpers.
- **Request-body limits split into two distinct knobs** — `AppConfig.max_upload_size` previously capped *every* request body (JSON, text, urlencoded, and multipart), conflating two concerns under one name. It is now the **multipart-total** ceiling only — the cumulative byte size of `multipart/form-data` parts, enforced by the multipart parser. A new `AppConfig.max_request_body_size` (default 16 MB) is the **general** envelope, enforced in `Request.stream()` for every content type before bytes are joined into RAM (reject-before-OOM). Both default to 16 MB, so default configs see no net behavior change; `max_upload_size` must be `<=` `max_request_body_size` (validated at construction with a `ConfigurationError`). Overridable via `CHIRP_MAX_REQUEST_BODY_SIZE`.

    **Removal** — The long-dead `AppConfig.max_content_length` (documented as the body limit but never actually enforced) has been removed in favor of the now-enforced `max_request_body_size`.

    **Migration** — If you relied on `max_upload_size` to cap non-multipart bodies (JSON/text), set `max_request_body_size` to the same value; otherwise such bodies revert to the 16 MB default cap.

    **`UploadFile` metadata is immutable again** — `UploadFile` is once more a frozen dataclass, so `filename`/`content_type`/`size` cannot be rebound (raises `FrozenInstanceError`), matching its docstring. The disk-spool backing introduced for streaming uploads is retained as a private field.
- **SQLite is now a real connection pool with write-only serialization.** File-backed SQLite databases open a small bounded pool of WAL-mode connections sized by `pool_size`; reads (`fetch`/`fetch_one`/`fetch_val`/`stream`/`fetch_raw`) acquire any free connection and run concurrently, while writes (`execute`/`execute_many`/`execute_script`/`transaction()`) serialize behind a single write lock. An open write transaction no longer stalls reads. In-memory databases (`sqlite:///:memory:`) keep using a single shared connection with all access serialized (a private `:memory:` connection is isolated and shared-cache memory mode is not concurrency-safe), so concurrent-reader throughput is a file-database (WAL) or PostgreSQL property — not Postgres-grade write concurrency. `DatabaseConfig.pool_size`, previously ignored for SQLite, now sizes the file-backed pool.

### Fixed

- **Caching restored for injected static HTML** — static `text/html` pages served by `StaticFiles` and rewritten by `HTMLInject` / `StreamingHTMLInject` / `AlpineInject` now keep conditional-GET. The middleware recomputes caching over the **post-injection** body: `Last-Modified` from the file mtime, a content-hash `ETag` (so it tracks both file and snippet changes), and a body-less `304` on `If-None-Match` / `If-Modified-Since`. A stable `ETag` is emitted only when the injected snippet is nonce-free; when a per-request CSP nonce is present the response carries `Last-Modified` only and never a stale `304`. `Range` / `Accept-Ranges` is intentionally dropped for injected HTML (on-disk byte offsets shift after injection) — clients fall back to a full `200`. Previously injected static HTML lost ETag / Last-Modified / 304 entirely (#198).
- **Contract checks** - Fixed a false-positive `middleware_signature` ERROR for function middleware. The check inspected `mw.__call__`, which on a plain function is the generic `(*args, **kwargs)` wrapper, so a valid `async def mw(request, next)` was wrongly reported as accepting 0 positional parameters (and would abort `chirp check` / debug `app.run()`). Function and method middleware are now inspected directly and named in diagnostics.
- **Contract diagnostics** - Corrected contract category severity guidance against the checker source and updated Suspense `defer_falsy` docs to prefer the `deferred` template test or pending-key set.
- **Examples** - Brought every shipped example to contract-clean: fixed SSE wiring in `sse`, `tools`, and `ollama` (moved `sse-swap` off the `sse-connect` element and added `hx-disinherit` scope isolation) and a render-breaking icon name in the `shell_oob` dashboard. Added a `shell_oob` smoke test and a repository-wide test asserting every `examples/**/app.py` passes the hypermedia contract check with zero errors, so a new example cannot ship with a broken contract.
- **Shapes — `shapecheck` soundness and bounded-compiler hardening.** A wave of `@shape` correctness fixes for defects that produced false contract failures or silently degraded runtime behavior. **`shapecheck`** no longer false-flags reads of a `nested()` relationship root or reads in a child block bound to a different Shape, attributes a genuine under-fetch to the innermost block where the read lives rather than a bound ancestor, and now actually invokes `Shape.validate(cls)`'s nested/scope checks at `app.check()` startup. **The bounded nested compiler** now preserves a child's `ORDER BY` and compiles a per-parent `LIMIT` into a window-function top-N — so "top 5 recent comments per card" is no longer silently "all comments, arbitrary order" — fails loud at startup on inexpressible cases, and chunks parent keys to a driver-safe limit so a level with tens of thousands of distinct parents no longer crashes on SQLite's variable cap (query count stays independent of *child row count*). **Tenant scope** fails loud at startup when a scoped Shape's SQL is un-injectable (derived-table/subquery `FROM`, opaque/compound queries) or already carries an author-written scope predicate, closing cases that previously passed `app.check()` and then crashed or under-scoped at runtime; scope-column matching is word-boundary anchored (so `community_id` cannot mis-match `community_id_legacy`) and aware of SQL comments and string literals.

    **Note** — `app.override_contract_severity("shapecheck", ...)` operates on the **whole category**: softening it to quiet over-fetch also demotes registry-drift, under-fetch, and un-injectable-scope from ERROR. The Shapes guide's severity-lever example is corrected to call this out. (#166/#167/#169/#173)
- **`Stream` rendering no longer blocks concurrent requests.** A slow or CPU-bound `Stream` render previously iterated kida's synchronous render generator inline on the event loop, so one heavy `Stream` stalled every other in-flight request for the duration of each chunk's compilation. `render_stream_async` now drives the kida generator on a dedicated worker thread and bridges each chunk back to the loop through a bounded queue, so the loop stays free for concurrent tasks while the render computes. Progressive flush is preserved (chunks still stream out incrementally, shell-first), back-pressure keeps memory bounded, mid-stream render errors still surface to the response, and a client disconnect joins the worker thread so it cannot leak. ([#179](https://github.com/lbliii/chirp/issues/179))
- **`Suspense` rendering no longer blocks concurrent requests.** A slow or CPU-bound `Suspense` render previously called kida's synchronous `template.render()` (shell) and `template.render_block()` (each deferred block, plus the error fallback) inline on the event loop, so one heavy `Suspense` stalled every other in-flight request for the duration of each render — the same DoS class closed for `Stream` in #179, but for the headline streaming feature. Each discrete render is now driven off the loop via `anyio.to_thread.run_sync` (with the request/CSP-nonce contextvars copied onto the worker), so the loop stays free for concurrent tasks while a render computes. This now covers the full `LayoutSuspense` path used by filesystem-pages apps that ship a `_layout.html`: the layout-chain wrap render (`render_with_layouts` once per layout) and the OOB streams chained onto the response (layout sidebar/breadcrumb/title blocks and shell-actions refresh on boosted navigation) all render off-loop too — previously only the page body did, so a heavy `_layout.html` or a heavy layout OOB region still froze the loop. Shell-first delivery and per-block OOB flush are preserved exactly — the shell streams first, then one OOB chunk per deferred block as its awaitable resolves — and `get_request()` plus the live CSP nonce still resolve inside template globals/filters during the render. Block discovery (`_find_deferred_blocks`) is untouched. ([#193](https://github.com/lbliii/chirp/issues/193))
- **`chirp new` (chirpui layout) now ships htmx.** The generated chirpui dashboard uses `hx-*` and the htmx SSE extension, but the layout shipped no htmx script — so the documented example was dead in a browser. The layout now provisions `htmx.org` + `htmx-ext-sse` in `<head>`, symmetric with how Chirp provisions Alpine.
- The `chirp new` chirp-ui scaffold no longer ships a CSP posture that silently
  breaks Alpine. It previously set `alpine_csp=True` to satisfy the `csp_nonce`
  contract after `'unsafe-inline'` was dropped from the default CSP, but the
  `@alpinejs/csp` build forbids the inline Alpine expressions chirp-ui components
  rely on (modal `x-data` factory calls, dropdown/sidebar/tray inline
  `@click`/`x-show`/`:class`), so those components died in the browser (CORS masks
  the error). The scaffold now runs the normal Alpine build under a per-request
  nonce CSP via `csp_nonce_enabled=True`, which auto-wires `CSPNonceMiddleware`
  (with `'unsafe-eval'` for Alpine) — keeping the `csp_nonce` contract clean while
  chirp-ui interactivity actually works. ([#196](https://github.com/lbliii/chirp/issues/196))
- `Suspense` now isolates deferred-block failures: when one awaitable data source raises, its block renders an error indicator while sibling deferred blocks bound to *other* keys still resolve and render real data. Previously a single failure aborted the whole task group and swept every pending block into an error indicator (all-or-nothing). The resolver also now catches `Exception` per key rather than `BaseException`, so `CancelledError`/`KeyboardInterrupt`/`SystemExit` propagate as expected.
- `use_chirp_ui(app)` now owns the "chirp-ui needs a working CSP" fact, so a chirp-ui
  app survives secure-by-default with **no hand-written Content-Security-Policy**.
  chirp-ui drives its shell with Alpine, which evaluates expressions as JS (needs
  `script-src 'unsafe-eval'`) and toggles visibility via inline `style="display:none"`
  attributes that **cannot be nonced** (needs `style-src 'unsafe-inline'`). The default
  CSP forbids both, which silently killed the entire interactive shell — collapse,
  dropdowns, theme toggle, modals, command palette — with no console error (CORS masks
  it). `use_chirp_ui` now flips `csp_nonce_enabled=True` in the same `bind_config` that
  auto-enables Alpine, so the compiler wires `CSPNonceMiddleware` as the single CSP
  authority: a per-request nonce `script-src` plus `'unsafe-eval'`, and a new
  `style-src 'self' 'unsafe-inline'` (the irreducible relaxation scoped to style-src
  only — script-src stays nonce-only). `CSPNonceMiddleware` gains a public
  `style_unsafe_inline: bool` constructor parameter for this; the compiler sets it the
  same way it sets `unsafe_eval` (`config.alpine and not config.alpine_csp`). A new
  env-aware built-in contract check, category `chirpui_csp`, **fails loud** at
  `app.check()` time (ERROR in production, WARNING in staging, silent in development)
  when a chirp-ui app's effective CSP would still kill Alpine — e.g. a conflicting
  static `SecurityHeadersMiddleware` policy that forbids the inline bootstrap/eval or
  inline style — instead of letting the invisible browser failure happen. Non-chirp-ui
  apps are unaffected (the check no-ops). The `lucky_cat` example drops its ~20-line
  hand-written `_CHIRP_UI_CSP` workaround and relies on the framework, keeping only a
  bare `SecurityHeadersMiddleware(content_security_policy=None)` for the
  clickjacking/MIME/referrer headers. ([#233](https://github.com/lbliii/chirp/issues/233))

### Security

- **SSE responses now default to same-origin.** `EventStream` no longer emits a hardcoded `Access-Control-Allow-Origin: *` header that silently bypassed the CORS middleware. Opt into a specific cross-origin policy with `EventStream(gen(), allow_origin="https://app.example.com")`, which also sets `Vary: Origin`.

    **Migration** — Apps that relied on the implicit `Access-Control-Allow-Origin: *` for cross-origin SSE must now opt in explicitly with `EventStream(gen(), allow_origin="https://app.example.com")`. Same-origin SSE needs no change.
- **Static file bodies now stream from disk instead of loading into memory.** `StaticFiles` previously called `file_path.read_bytes()` on every request, buffering the entire file in RAM with no cap — the same unbounded-RAM DoS class as unbounded uploads. Files at or above `AppConfig.static_stream_threshold` (default 1 MiB) now stream from disk in chunks, so large static GETs no longer grow worker RSS unboundedly; smaller files are still read in one shot to keep latency unchanged. A new `static_streaming` contract category warns when the threshold is misconfigured. ([#178](https://github.com/lbliii/chirp/issues/178)) `FileResponse` composes with the response middleware stack: `SecurityHeadersMiddleware` and `CSPNonceMiddleware` still apply X-Frame-Options / X-Content-Type-Options / Referrer-Policy / CSP to static HTML pages (and custom 404s), and `HTMLInject` / `AlpineInject` still inject into static HTML.
- **Uploads** - File uploads now spool to disk past a configurable threshold instead of buffering the whole file in RAM, and three new `AppConfig` limits harden the request pipeline: `max_upload_size` (default 16 MB) rejects an oversize body with **413 Payload Too Large** *before* the chunks are joined into memory; `upload_spool_threshold` (default 1 MB) controls when an `UploadFile` rolls over to a temp file; and `max_upload_parts` (default 1000) caps multipart parts to stop multipart bombs. `UploadFile.save()` now streams to disk in chunks and sanitizes the destination basename, rejecting path traversal (`../`, absolute paths, Windows separators, NUL). Spooled temp files are cleaned up at request teardown. All three limits are overridable via `CHIRP_MAX_UPLOAD_SIZE`, `CHIRP_UPLOAD_SPOOL_THRESHOLD`, and `CHIRP_MAX_UPLOAD_PARTS`.
- CSP nonces now stay live across the SSE / `EventStream` drain. Previously
  `CSPNonceMiddleware` reset its nonce `ContextVar` in a `finally` the instant the
  handler returned — before `handle_sse` produced any event — so a framework inline
  script emitted inside a yielded `Fragment` (`format_oob_script`,
  `alpine_json_config`, `safe_data_helper`, or `<script nonce="{{ csp_nonce() }}">`)
  streamed with a dead/empty nonce, the same lifecycle bug fixed for `Suspense` in
  #181. The live nonce is now captured at negotiation time, carried on `SSEResponse`,
  and re-established inside the SSE producer task for the connection's whole lifetime
  (mirroring the `StreamingResponse` drain in `send_streaming_response`), so every
  event on a long-lived stream renders with the stable per-request nonce.
  ([#194](https://github.com/lbliii/chirp/issues/194))
- CSP nonces now stay live across the Suspense streaming drain. Previously
  `CSPNonceMiddleware` reset its nonce `ContextVar` in a `finally` the instant the
  handler returned — before any `StreamingResponse` (e.g. `Suspense`) chunk was
  produced — so framework-emitted inline scripts (`format_oob_script`) streamed
  with a dead/empty nonce. The nonce is now carried on `StreamingResponse` and
  re-established in `send_streaming_response` (mirroring the existing
  `request_context` lifecycle), and threaded through every framework inline-script
  emitter (`format_oob_script`, `alpine_snippet`/`safe_data_helper`,
  `alpine_json_config`). As a result the default CSP (both
  `SecurityHeadersConfig.content_security_policy` and the production HSTS-path CSP)
  drops `'unsafe-inline'` from `script-src`. A new `csp_nonce` contract category
  ERRORs when a framework inline script would be un-nonced under an
  inline-forbidding CSP (e.g. `alpine=True` under a nonce-only policy without the
  `@alpinejs/csp` build). ([#181](https://github.com/lbliii/chirp/issues/181))

    **Migration** — The default CSP now omits `'unsafe-inline'` from `script-src`, so framework inline scripts (Alpine bootstrap, Suspense/SSE OOB scripts, view-transitions, islands, speculation rules) require a per-request nonce. Enable a nonce mechanism — `CSPNonceMiddleware` or `AppConfig(csp_nonce_enabled=True)`; `use_chirp_ui()` and every `chirp new` scaffold now wire this for you, and a standard `alpine=True` app no longer needs `alpine_csp=True`. `app.check()` fails loud (ERROR in production, WARNING in staging) when an inline script would be un-nonced, naming the fix. Apps that intentionally keep un-nonced inline scripts must re-add `'unsafe-inline'` to their own `script-src`.
- Every framework-emitted inline `<script>` now carries the live per-request CSP
  nonce, not just Alpine. Each compile-time injection — the Alpine `safeData`
  bootstrap, `safe_target`, `sse_lifecycle`, `delegation`, the `view_transitions`
  script, the `islands` runtime, and the `speculation_rules`
  `<script type="speculationrules">` — is built through a per-request snippet
  factory (`nonce -> snippet`) that `HTMLInject` resolves from `csp_nonce()` in
  request scope, on both the buffered full-page path and the streaming/Suspense
  path. Combined with the Suspense (#181) and SSE (#194) lifecycle fixes, every
  framework inline script survives a strict nonce-only CSP when a nonce mechanism
  is active (`CSPNonceMiddleware` or `AppConfig(csp_nonce_enabled=True)`), so a
  standard `alpine=True` app no longer needs `alpine_csp=True`. View-transitions
  HEAD markup is a `<meta>`/`<style>` pair governed by `style-src`, not
  `script-src`, so it is left un-nonced by design. The `csp_nonce` contract was a
  permanent no-op; it now flags the genuinely un-nonceable case — an
  inline-forbidding CSP (a `script-src` without `'unsafe-inline'`) in force with no
  per-request nonce mechanism while a framework inline-script feature is enabled —
  with env-aware severity (ERROR in production, WARNING in staging, silent in
  development), naming the fix (enable `CSPNonceMiddleware`/`csp_nonce_enabled`, or
  add `'unsafe-inline'`). ([#195](https://github.com/lbliii/chirp/issues/195))


# Changelog

All notable changes to chirp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.1] — 2026-05-30

### Changed

- **DevTools** — Chirp DevTools now uses native debug runtime wiring and server-owned EventStream traces instead of replacing browser `EventSource`.

    Internal debug/reload routes are classified as framework-owned, hidden from normal DevTools activity by default, and protected from application route collisions at freeze time. Debug responses also include typed return traces so DevTools can report the negotiated `Template`, `Fragment`, `PageComposition`, `OOB`, `Suspense`, `Stream`, `EventStream`, `Action`, or `ValidationError` branch without parsing response bodies.

### Fixed

- `_actions.py` dispatch now passes the current `Request` into action functions and request-aware `app.provide()` factories, preserving request-scoped service context for filesystem actions.

## [0.7.0] — 2026-05-14

### Added

- **Benchmarks** — added a networked template-rendering workload to the Chirp, FastAPI, and Flask comparison runner.
- **Fragment safety** — `app.check()` now warns when a fragment block depends on imports or bindings declared only inside an ancestor block, and `chirp.testing` adds `RouteSmokeCase` / `assert_route_smoke` for full-page and fragment route smoke checks.
- **Request URL scope** — `RequestUrlScope`, `request.with_url_scope(...)`, `request.scoped_url(path)`, and `request.url_for(...)` let middleware generate tenant/base-path public URLs without changing `app.url_for(...)` or rewriting rendered HTML.
- **`csrf_form` contract check** — when `CSRFMiddleware` is active, `app.check()` now warns on static mutating forms that do not render `csrf_field()`, call `csrf_token()`, or include an `_csrf_token` field.
- Added drift guards that keep `docs/public-api.md` aligned with `_API_STATUS`, require every `AppConfig` field to appear in the configuration guide, and require changelog fragments for branch changes to the top-level public API registry.
- Added provisional `DeferredCache` for explicit server-side reuse of Suspense deferred values, including TTL expiry and same-key in-flight deduplication.
- Benchmark comparison runner now covers SQLite DB workloads and Starlette/Litestar targets, with report headers that record Python version and GIL/free-threaded mode for 3.14 vs 3.14t comparisons.
- Document the 2026-05-03 release-readiness gate run, mark completed/stale planning docs with current status, complete the initial 1.0 public surface, `AppConfig`, and stable error-message audits, correct the configuration guide, promote `JSONResponse` to stable, and make selected routing/forms/session errors more actionable.
- Reactive apps can now expose `reactive_index`, `reactive_emitted_paths`, `reactive_audience_scopes`, and `reactive_connection_scopes` through `app.set_contract_check_data()` so `app.check()` can warn about emitted paths missing from the `DependencyIndex` and audience-filtered scopes that lack `ConnectionInfo` subscribers.

### Changed

- **Pounce 0.7 operator guidance** — documented the `bengal-pounce>=0.7.0` production boundary, paired `chirp check` with `pounce check`, described Pounce config inspection commands, clarified that `pounce.toml` is Pounce-native today while `app.run()` and `chirp run` use `AppConfig`, and deferred trusted proxy, compression, and introspection `AppConfig` fields pending a separate security-facing API decision.
- **Scoped auth redirects** — `@login_required` and `@requires` now preserve `RequestUrlScope` in generated `?next=` login redirects, so tenant/base-path middleware keeps users on the public URL after login.
- Raised Chirp's optional `ui` extra, development example dependency, and new scaffolded project floor to `chirp-ui>=0.9.0`.
- Require `kida-templates>=0.9.0`, preserve Chirp's missing-block `KeyError` behavior when Kida reports missing blocks with its typed runtime error, and surface Kida 0.9 component-call, dotted context-contract, literal-attribute, escape-audit, and privacy-lint diagnostics through `app.check()`.
- `EventStream` now matches the documented htmx SSE default for yielded `Fragment` values: fragments without an explicit target emit on the `message` channel, while targeted fragments still use their target as the event name. The `sse_scope()` macro and bundled examples now listen on `message` by default, and the SSE cross-reference contract can infer literal `SSEEvent(event=...)` and `Fragment(target=...)` yields from route source.

### Fixed

- Aligned `url_for()` and contract route matching with typed route converters. `url_for()` now rejects path values that do not match the route converter, and `app.check()` no longer treats literal URLs like `/users/alice` as valid matches for `/users/{id:int}`.
- Fixed lifespan startup cleanup so a database connection opened during startup is disconnected when a later startup hook or migration step fails before `lifespan.startup.complete`.
- Fixed router parameter matching so typed and string parameter routes at the same path depth no longer shadow each other or reuse the wrong parameter name. Route parsing now rejects malformed parameter segments, unknown converters, non-final `{name:path}` converters, and duplicate route shapes that differ only by parameter name.
- SQLite migrations now wrap the migration SQL and tracking-table insert in one explicit transaction, so a failed multi-statement migration does not leave partially-created tables or a stale migration record.
- `CacheMiddleware` now preserves cached response headers and content type on cache hits instead of reconstructing every cached response as bare `text/html`.
- `app.check()` now reports `fragment_target_scan` errors when a page template cannot be inspected during fragment target orphan checks, instead of silently skipping that template and potentially hiding stale or misspelled target registrations.
- `chirp security-check` now matches `app.check()` host validation by allowing wildcard `allowed_hosts` in development while still failing wildcard hosts outside development.
- Debug browser reload now boots idempotently, skips htmx swaps, honors `reload_include=()` as an opt-out, and no longer passes browser asset suffixes to Pounce as process-reload extensions.

### Security

- **Middleware security defaults** — auth rate limiting now uses the socket client address by default instead of trusting `X-Forwarded-For`, credentialed wildcard CORS is rejected, and `app.check()` flags wildcard `allowed_hosts` outside development.

    **Migration** — Apps behind a trusted proxy that intentionally key auth rate limits by `X-Forwarded-For` must pass `AuthRateLimitConfig(key_header="x-forwarded-for")`; credentialed CORS must list explicit origins.
- **SSE and markdown trust boundaries** — `SSEEvent` now rejects event names and IDs containing CR, LF, or NUL characters, rejects negative retry values, and normalizes carriage returns in data frames. `MarkdownRenderer` and `register_markdown_filter()` now sanitize unsafe HTML, event attributes, and unsafe link/image URLs by default.

    **Migration** — Trusted markdown that intentionally preserves raw HTML can pass `sanitize=False`. Apps constructing `SSEEvent(event=...)` or `SSEEvent(id=...)` must pass single-line field values.
- `CacheMiddleware` now bypasses cache reads and writes for GET requests carrying `Cookie` or `Authorization` headers, preventing default site-wide caching from replaying authenticated or session-specific HTML.
- `chirp freeze` now rejects expanded URLs containing `.` or `..` path segments before mapping them to output files. Unsafe `freeze_params` values are reported in `FreezeResult.errors` and are not written outside the target output directory.

## [0.6.0] — 2026-05-02

### Added

- **DevTools Swap Doctor** — expanded htmx activity rows now explain swap behavior with effective `hx-*` inheritance, selector-match checks, target presence, render intent, render-plan context, broad-target warnings, full-document fragment smells, and no-op swap detection. Request records are correlated by XHR when available so overlapping htmx requests keep their diagnostics attached to the right row. New scaffolded apps include `AGENTS.md` guidance for activating DevTools, and browser-capable agents can discover the diagnostics API with `window.ChirpHtmxDebug.help()`.
- **Hero-app enablers** — added `Page.mounted(...)`, top-level `JSONResponse`, repeated `form_from()` list binding, contract coverage counters, and stricter testing helpers for full-page/fragment/id assertions.
- **Named routes and `url_for`** — Routes mounted via `app.mount_pages()` now carry a default dotted name (`/contacts/{contact_id}` → `"contacts.contact_id"`, `/` → `"index"`). Override per-page by setting `name = "…"` at module level in `page.py`. Reverse names to URLs with `app.url_for("contacts.contact_id", contact_id=42)` or the matching `{{ url_for(...) }}` template global (registered via `setdefault`, so user overrides still win). Path params are percent-encoded; remaining kwargs become a urlencoded query string; `None` values are dropped. A new `route_names` contract check fails `app.check()` when two routes at *different* paths claim the same name (method variants at the same path are not collisions).
- **`app.mount_app(prefix, sub_app)`** — hoist a pre-freeze Chirp `App` into a parent app at a URL prefix. Sub-app's pending routes are path-prefixed, middleware / hooks / loaders / contract checks are appended, and template globals / filters / providers / error handlers / severity overrides merge with parent-wins semantics (dropped entries surface as INFO issues in a new `mount_app_merge` contract category). Sub-app is **consumed** — `sub_app.freeze()` / `sub_app.run()` raise `RuntimeError` after the mount, so you can't accidentally serve a half-mounted standalone runtime. Designed for transitional migrations where two full apps need to share one port; see `docs/routing/mounting.md` and `docs/rfcs/005-mount-app.md` for merge rules and unsupported sub-app state.
- **`chirp check --coverage`** — show contract coverage counters for POST form contracts, mounted page contracts, app-shell targets, and OOB regions.
- **`examples/chirpui/forum_shell`** — added a compact forum/PBP reference app showing mounted pages, app-shell OOB state, typed reply forms with repeated mention fields, and a JSON mention-search endpoint.
- **`page_handlers` contract check** — `app.check()` now fails fast at startup when a `page.py` defines no recognised HTTP method handler (`get`/`post`/… or `handler`), instead of letting requests hit a 404/500 at runtime. Handler-shaped typos (`def handle`, `def GET`, `def index`) emit a WARNING; a fully missing handler emits an ERROR. Tune via `app.override_contract_severity("page_handlers", …)`.
- Add an in-process Chirp core benchmark suite for template, fragment, OOB, Suspense, SSE fanout, and filesystem route dispatch workloads with reproducible JSON output.
- Document the top-level public API stability tiers and add tests that snapshot exported names and require every export to have a stability classification.
- Grouped `app.check()` terminal output by contract concern and included total elapsed time in contract check reports.
- Replaced the legacy roadmap narrative with an executable maturity roadmap for 0.5.x reliability, contracts, performance, API discipline, and the PBP forum proof app.

### Changed

- **In-repo examples migrated to `url_for`** — every chirpui and standalone example now reverses URLs through `app.url_for` / `{{ url_for(...) }}` instead of hardcoded `hx-get`/`hx-post`/… strings. `rg 'hx-(get|post|put|delete|patch)="/' examples/` drops from 88 hits to 3 (the remaining hits are an intentional 404 sentinel URL and two test assertions verifying rendered HTML). Route names follow the RFC 003 dotted-path convention for `@app.route(...)` handlers (`index`, `tasks.add`, `tasks.move`, etc.).
- **Railway env config** — `AppConfig.from_env()` now falls back to Railway's `PORT`, binds to `0.0.0.0` when a Railway environment is detected, and includes `RAILWAY_PUBLIC_DOMAIN` plus `healthcheck.railway.app` in `allowed_hosts` when `CHIRP_ALLOWED_HOSTS` is not set.
- **`Page(...)` TypeError ergonomics** — Calling `Page("page.html", **ctx)` without a block name now raises a `TypeError` that points at `Template("page.html", **ctx)` (the correct type for full-page renders without htmx negotiation) and references the return-values decision tree. Users reaching for `Page` when they mean `Template` no longer get a generic "missing positional argument" traceback.
- Raised Chirp's `chirp-ui` dependency floor to `>=0.6.0` for the optional `ui` extra, development example tests, and newly scaffolded projects. `use_chirp_ui(app)` now injects ChirpUI's packaged `themes/app-theme-starter.css` after `chirpui.css` so the theme toggle has light/dark/system tokens by default, and new scaffolds load app-owned `static/theme.css` as the override slot. Chirp now surfaces ChirpUI 0.6 manifest/runtime metadata in `app.check()`, emits an informational `chirpui_runtime` issue when app templates import ChirpUI without `use_chirp_ui(app)`, and updates the mounted-pages shell example to use `nav_tree(branch_mode="linked")`.
- Raised Chirp's docs build dependency floor to `bengal>=0.3.2` so non-workspace documentation builds pick up the latest Bengal production-build fixes.

### Fixed

- **Cache keys** — default cache keys now include the query string and htmx response shape so paginated forum views, full-page responses, boosted responses, and local fragments do not collide under `CacheMiddleware`.
- **Form contracts** — block-scoped `FormContract` validation now respects nested template blocks and Kida control tags instead of truncating at the first nested `{% endblock %}`.
- **Kida 0.8** — bump the minimum `kida-templates` version to `>=0.8.0` and resolve relative template references (`./`, `../`) plus configured `@alias/` prefixes before dead-template and inherited swap-safety analysis.
- **Shell outlets** — boosted navigation into an app-shell outlet now keeps responses selectable by inherited `hx-select` contracts, with `chirpui/app_shell_layout.html` layouts using the registered `chirpui-app-shell` preset automatically and `app.check()` warning when a broad `hx-target`/`hx-select` shell is missing `{# outlet: ... #}` metadata.
- Fixed example drift against current Kida and Chirp contracts, including Hacker News nested macros, Kanban anonymous-user rendering, Survey default form values, and Kanban startup contract errors.
- Made `ReactiveBus.emit_sync()` and `ReactiveBus.close()` hand off cross-thread queue delivery to each subscriber's owning event loop instead of mutating `asyncio.Queue` from arbitrary threads.
- Make `ToolEventBus`, the PostgreSQL LISTEN helper, and the standalone chat example hand cross-thread event delivery back to each subscriber's owning event loop.

## [0.5.0] — 2026-04-23

### Added

- **Alpine on streaming HTML** — `AlpineInject` rewrites `StreamingResponse` bodies (e.g. `Suspense`) to insert the Alpine bundle before `</body>`, with the same deduplication as buffered pages.
- **Ancestor block pruning** — `_find_deferred_blocks` now drops blocks whose `depends_on` is a strict superset of another matched block, preventing large parent blocks (e.g. `page_content`) from being re-rendered as wasted OOB chunks.
- **Concurrency stress tests** — 25 new tests covering all Lock-protected modules (bus, cache, rate-limiter, lockout, OOB registry), ContextVar isolation, and database pool stress.
- **Configurable queue depth** — `ReactiveBus(maxsize=N)` controls per-subscriber queue size (default 256, unchanged).
- **Contract checks — source-level SSE event inference** — ``check_sse_event_crossref`` now AST-walks each ``@contract(returns=SSEContract(...))`` handler for literal ``SSEEvent(event="...")`` and ``Fragment(target="...")`` yields. A ``sse-swap="X"`` on a child of ``sse-connect`` that matches neither the declared ``event_types`` nor any inferred literal is promoted from ``WARNING`` to ``ERROR`` at startup — the silent-mismatch class of bug (htmx drops unmatched events) now fails loud. Handlers with non-literal ``event=`` / ``target=`` (variable, f-string, or function call) disable inference for that route; an ``INFO`` issue is emitted so operators can annotate ``SSEContract.event_types`` to restore fail-loud coverage.
- **Form action contract** — `chirp check` reports `<form action="/path" method="post">` targets that lack a `FormContract` declaration.
- **Layout `HX-Target` + outlet** — `LayoutChain.find_start_index_for_target` matches `{# outlet: element_id #}` as well as `{# target: #}`, so boosted `HX-Target: #main` resolves for chirp-ui app shells (`{# target: body #}` + `{# outlet: main #}`).
- **Layouts, Alpine, & Reactive docs** — Filesystem routing (outlet + `main`), route contract reference, streaming HTML + Suspense + Alpine, built-in middleware, ReactiveBus API, DependencyIndex, derived paths, observability counters, thread safety stress test coverage, contract checks (reactive_block, reactive_cycle, oob_target, form_action), SSE monitoring, and shell tabs.
- **Native fragment blocks — ``{% fragment name %}...{% end %}``** — Chirp now recognises kida 0.6.0+'s native fragment directive as a swap-only target: the block body is suppressed during a full-template render (``Template("p.html", ...)``) and only emits content when addressed by ``Fragment("p.html", "name", ...)``, the ``/_frag{path}?_b=name`` dispatcher, or a ``{% fragment %}`` target in a ``PageShellContract``. Use this instead of the ``{% block %}`` + ``{% if foo is defined %}`` workaround for blocks that should never render inline — e.g. success panels, SSE payloads, OOB swap targets.

  **Contract rules updated to match** — ``check_unreachable_blocks`` no longer flags ``fragment=True`` blocks as unreachable from composition roots: they are unreachable *by design*. Every other rule (``check_fragment_target_orphans``, ``check_page_shell_contracts``, ``rules_sse`` cross-reference) walks ``block_metadata()`` and already treats fragment and regular blocks identically.
- **OOB target contract** — `chirp check` warns when `hx-swap-oob` elements reference IDs not found in any template.
- **Reactive contract rules** — `chirp check` validates that `DependencyIndex` block references point to real template blocks and that derivation graphs are acyclic.
- **ReactiveBus observability** — `emitted_count`, `dropped_count`, and `subscriber_count` properties for monitoring event throughput and back-pressure.
- **Suspense templates docs** — Document `{% if key is not none %}` / `__chirp_defer_pending__` instead of bare `{% if key %}` (falsy empty results look like perpetual skeletons). Updated `return-values.md`, streaming guide, `CLAUDE.md`, and API reference.
- **`Suspense.defer_blocks`** — optional explicit list of blocks to re-render as OOB chunks, bypassing `block_metadata()` static analysis. Use when deferred values are passed through macro arguments that the analyzer can't trace.
- **`__chirp_defer_pending__` / `CHIRP_DEFER_PENDING_KEY`** — Suspense shell renders (and sync-only Suspense renders) inject a `frozenset` of context key names still awaiting resolution; deferred block re-renders use an empty frozenset. Templates can branch on membership instead of overloading `None` / truthiness.
- **`alpine_json_config` docs** — Chirp `CLAUDE.md`, Alpine guide, and built-in middleware reference document the template global and its relationship to `AlpineInject`.
- **`alpine_json_config` template global** — when `alpine=True`, templates can emit `<script type="application/json">` tags with safely escaped ids and JSON for Alpine components (`alpine_json_config("my-id", data)`).
- **`chirp.errors.BlockNotFoundError`** — Multi-inherits from `ChirpError` and `KeyError`, so existing `except KeyError` handlers (including Kida's documented `render_block` contract) continue to catch it. Carries `template`, `block`, and `region` attributes for structured error handling.
- **`register_oob_region(..., optional=True)`** — Opt-out for shell regions that legitimately appear in only some layouts. Optional orphans stay at `WARNING`; at render time, optional regions missing from the current layout are silently dropped (not emitted as empty OOB wrappers). `chirp.ext.chirp_ui`'s auto-registered breadcrumb, sidebar, title, and shell-actions regions all default to `optional=True`.

### Changed

- **Breaking — SSE event-name default** — ``EventStream`` now emits yielded ``Fragment`` payloads as **unnamed** SSE frames (matching htmx's default ``message`` event name). Previously the wire frame defaulted to ``event: fragment``, requiring every consumer to declare ``sse-swap="fragment"`` — a chirp-specific quirk that silently broke stock htmx-sse snippets.

  **Migration** — In templates, change ``sse-swap="fragment"`` to ``sse-swap="message"`` (htmx-sse requires the attribute to be present to wire up the listener; ``"message"`` is the default event name emitted by untargeted ``Fragment`` yields). The ``chirp/sse.html`` macro now defaults to ``swap="message"``; pass ``sse_scope("/events", swap="status")`` to opt into a named channel. To keep the old wire shape explicitly, yield ``SSEEvent(data=rendered_fragment, event="fragment")`` instead of a bare ``Fragment``, or pass ``target="fragment"`` on the Fragment.
- **Chirp-ui integration** — Suppress ``UserWarning`` when optional chirp-ui implementations replace Chirp’s built-in filter stubs (detected via ``__module__`` prefix).

  **Contract checks** — ``Template``/``Page``/``Suspense``/``Fragment`` reference scan includes ``Page`` and ``Suspense`` paths; filesystem routes expose the original handler as ``Route.page_source_handler`` so dead-template and fragment checks see user source inside the async page wrapper. Import ``make_route_link_attrs`` via ``importlib`` when wiring ``route_link_attrs`` for ty-friendly optional installs.

  **Context cascade** — Deduplicate identical override notices; omit INFO when child providers intentionally override ``shell_actions``, ``shell_mode``, or ``Components``.
- **Dependencies** — `kida-templates>=0.6.0` (bumped from `>=0.3.0`), `bengal-pounce>=0.6.0` (bumped from `>=0.4.0`).
- **Scaffold template** — `chirp new` now pins `bengal-chirp>=0.2.0` (was `>=0.1.9`). Existing projects are unaffected; new projects get the latest contract fixes and Alpine injection improvements from 0.2.x.
- **OOB render errors fail loud** — `execute_render_plan` previously caught every exception raised while rendering an OOB region and substituted `html = ""`, producing empty swaps that wiped existing DOM content. Missing blocks now raise `chirp.errors.BlockNotFoundError`; genuine render errors (context `KeyError`, filter errors) propagate to the route error handler. See `docs/guides/oob-registry.md`.
- **Orphan OOB registrations error at freeze** — `app.check()` now emits `Severity.ERROR` (was `WARNING`) when the OOB registry contains a block no layout template defines. Non-optional orphans block debug-mode freeze; `app.override_contract_severity("oob_registry", Severity.WARNING)` restores prior behavior globally. Add `optional=True` to `register_oob_region()` calls for regions that legitimately appear in only some layouts.
- **`AppConfig.strict_undefined` — `True` by default** — chirp now passes `strict_undefined` through to kida's `Environment`, matching kida 0.7.0's new default. Templates referencing a missing attribute/key raise `UndefinedError` instead of silently rendering empty. Opt out with `AppConfig(strict_undefined=False)` during migration; fix callsites with `obj.attr ?? ""`, `| default(...)`, or `{% if obj.attr is defined %}`.
- **chirp-ui floor bumped to `>=0.5.0`, kida-templates to `>=0.7.0`** — picks up chirp-ui 0.5 (agent-grounding manifest, composite contract tests, `@layer chirpui.*` cascade public API, `set_strict("auto")` + `CHIRP_UI_DEV`), kida 0.7 (`strict_undefined=True` default, Jinja2 parser hints), and chirp-ui 0.4 sharp-edges audit. `use_chirp_ui(app, strict="auto")` now delegates to the `CHIRP_UI_DEV` env var so dev hosts opt in once without code changes. Per-request `_ChirpUIStrictMiddleware` retired — chirp-ui strict mode is now set once at `use_chirp_ui()` registration.
- Remove 49 no-op `from __future__ import annotations` imports (PEP 649 default on 3.14), add 11 TypedDicts for stable dict shapes in tools/debug modules, and convert 3 dispatch chains to `match/case`.

### Fixed

- **Route contract** — `chirp check` no longer reports missing `_meta.py` for routes whose `_meta.py` defines only `meta()` (dynamic metadata). Those routes register a meta provider at discovery time; the checker now treats that as satisfying the route metadata contract.

## [0.3.3] — 2026-03-30

### Fixed

- **CSP defaults** — `SecurityHeadersMiddleware` and `CSPNonceMiddleware` now allow `unpkg.com` (htmx), `cdn.jsdelivr.net` (Alpine.js), and inline scripts in the default `script-src`, fixing silent breakage of htmx/JS actions.

### Dependencies

- `chirp-ui>=0.2.3` (bumped from `>=0.2.2`)

## [0.3.2] — 2026-03-30

### Dependencies

- `chirp-ui>=0.2.2` (bumped from `>=0.2.1`)

## [0.3.1] — 2026-03-30

### Added

- **Speculation Rules API** — Auto-generate `<script type="speculationrules">` from route definitions with tiered opt-in via `AppConfig(speculation_rules=...)`: `False`/`"off"` (default), `True`/`"conservative"` (prefetch on hover), `"moderate"` (prefetch eagerly, prerender on hover), `"eager"` (prerender eagerly). XSS-safe JSON escaping in the injected script tag.
- **Invoker Commands validation** — `app.check()` now validates `commandfor` targets and `command` attribute values against the Invoker Commands spec, with negative lookbehind to avoid false positives on `data-command`/`data-commandfor`.
- **htmx 4.0 `<htmx-partial>` alignment** — `HX-Partial` header parsing on `Request`, fragment block resolution for partial requests, and contract validation for `<htmx-partial src="...">` routes.
- **Philosophy doc** — `docs/philosophy.md` coins "hypermedia-native" as Chirp's app style and documents the five core opinions.
- **CLAUDE.md** — Development guide for contributors and AI assistants.

### Changed

- **View Transitions** — Replaced the single boolean toggle with three tiers: `False`/`"off"` (inject nothing, now the default), `True`/`"htmx"` (htmx `globalViewTransitions` only), `"full"` (htmx JS + MPA CSS/meta for cross-document transitions). **Breaking:** default changed from `True` to `False`.
- **README** — Trimmed redundant sections; merged "Hypermedia-Native Python" and "What is Chirp?"; added Zoomies to the Bengal ecosystem table.

### Fixed

- **Suspense** — `format_oob_script` no longer double-nests OOB swap markup.
- **SSE fragment whitespace** — Trailing whitespace stripped from SSE data fields, fixing htmx table row parsing.
- **Markdown filter** — Renderer output is now marked safe to prevent Kida auto-escaping HTML.
- **Standalone examples** — Contacts edit URL reset after save; upload delete route reachable from HTML forms; dashboard/hackernews SSE restored (missing `worker_mode`); ollama chat form clears on submit and shows tools-used label in streaming mode.
- **Kanban template** — Replaced `loop.index` inside `{% call %}` with CSS `:nth-child(odd)` to work with Kida 0.3.0 scope isolation fix.

### Dependencies

- `kida-templates>=0.3.0` (unchanged minimum, but now tested against Kida 0.3.0 scope isolation)
- `bengal-pounce>=0.4.0` (unchanged minimum)

## [0.3.0] — 2026-03-25

### Added

- **Security middleware** — `AllowedHostsMiddleware` validates the `Host` header against a configurable allowlist, rejecting spoofed-host requests. `CSPNonceMiddleware` generates per-request `Content-Security-Policy` nonces accessible via `request.state["csp_nonce"]` and injected into templates.
- **Caching framework** — `chirp.cache` with a `CacheBackend` protocol and three backends: `MemoryCacheBackend`, `NullCacheBackend`, and `RedisCacheBackend`. Includes `CacheMiddleware` for response caching with a configurable key function, `default_cache_key()` / `vary_aware_cache_key()` helpers, and `Vary`-aware keying.
- **Plugin system** — `ChirpPlugin` protocol and `app.mount(prefix, plugin)` for distributing reusable middleware, routes, and template extensions as packages.
- **Schema migrations** — `chirp.data.schema` with introspection, diff, operation generation, and migration file output. `chirp makemigrations` CLI command auto-generates migration files from model changes.
- **Internationalization** — `chirp.i18n` with message catalogs, `LocaleMiddleware` for locale detection, number/date/currency formatting, and `t()` translation helpers wired into templates.
- **CLI** — `chirp makemigrations` and `chirp security-check` subcommands.
- **Vary contract rule** — `contracts.rules_vary` validates that responses include correct `Vary` headers when content depends on request headers.
- **SECURITY.md** — Vulnerability reporting policy.

### Changed

- **htmx headers** — `Request` and `Response` htmx header handling improved for correctness, inspired by django-htmx. `HX-Trigger`, `HX-Push-Url`, `HX-Replace-Url`, and related headers now follow the htmx spec more closely with proper JSON encoding and boolean handling.

### Dependencies

- No dependency changes (all new modules use stdlib or existing deps).

## [0.2.0] — 2026-03-23

### Added

- **Chirp devtools** — Modular debug overlay (inspector, activity, errors, swap highlight) with a split JS bundle under `chirp/server/devtools/`, replacing the monolithic injected debug script path.
- **View Transitions dev tooling** — Development helpers for debugging View Transitions alongside htmx navigation.
- **Browser dev reload** — Optional `AppConfig.dev_browser_reload`: SSE-driven browser refresh when watched files change (pairs with `reload_include` / `reload_dirs`).
- **Render plan snapshots** — Debug snapshot path for render plans (`server/debug/render_plan_snapshot`) for tests and diagnostics.
- **`ShellSubmitSurface`** — Exported type for shell action submit surfaces (`chirp` public API).
- **Shell regions** — Shell region metadata and related shell-action wiring updates.
- **Middleware** — `inject` middleware; layout-debug helpers for development.
- **SSE and logging** — SSE lifecycle and logging improvements aligned with Pounce.
- **Startup and terminal errors** — Clearer formatted messages for startup failures and terminal error output.
- **CLI** — `chirp new` / `chirp run` refinements and scaffold template modules.
- **Examples** — Reorganized into `examples/chirpui/` (chirp-ui apps) and `examples/standalone/` (minimal Chirp); updated `examples/README.md` and per-example docs.
- **Docs** — App shell, UI layers, SSE/streaming guides, layout patterns, and tutorial cross-links.

### Changed

- **Defaults** — `AppConfig.view_transitions` now defaults to `True` (was `False`). Set `view_transitions=False` for API-only apps or tests that require responses without injected View Transition markup/CSS.
- **Defaults** — `AppConfig.log_format` now defaults to `auto` (compact colored lines on a TTY, JSON when piped; aligned with Pounce). Use `CHIRP_LOG_FORMAT` with `auto`, `text`, or `json`.
- **htmx debug** — Wired through the new devtools implementation; large legacy debug script removed from the tree.
- **Contracts and negotiation** — Broader swap/layout/SSE/route-contract checks, template scanning, and content negotiation (including OOB-related paths).
- **Alpine server injection** — Adjustments to Alpine injection and related tests.
- **AI providers** — Internal provider wiring updates.

### Dependencies

- `kida-templates>=0.2.9`
- `bengal-pounce>=0.3.1` (public `PounceError` and related lifespan error exports)
- `chirp-ui>=0.2.1` (optional, for `chirp[ui]`)

## [0.1.9] — 2026-03-12

### Added

- **Route directory contract** — Filesystem routes now have a documented golden path around `_meta.py`, `_context.py`, `_actions.py`, and `_viewmodel.py`, plus section registration via `app.register_section()` for tabs, breadcrumbs, and shell metadata.
- **Route introspection** — Debug builds now expose `X-Chirp-Route-*` headers and a `/__chirp/routes` explorer for inspecting discovered routes, layouts, providers, actions, and route metadata.
- **Synthetic benchmark suite** — New `benchmark` extra, benchmark runners, and benchmark docs compare Chirp against FastAPI and Flask across JSON, CPU, fused sync, and mixed JSON+SSE workloads.

### Changed

- **Sync request path** — Chirp now exposes a fused sync path through `App.handle_sync()` and `SyncRequest`, with lazy query/cookie parsing and pre-encoded content types for simple request-response handlers.
- **Filesystem route ergonomics** — Route metadata, section bindings, shell context assembly, action dispatch, and view-model wiring are now part of the route contract and validated by `app.check()`.
- **CLI scaffolds** — `chirp new` now keeps its templates in dedicated modules, including updated shell and SSE scaffolds.

### Fixed

- **Sync handler execution** — Sync handlers now avoid blocking the event loop on the standard ASGI path while still enabling the faster fused path when a route is eligible.

### Dependencies

- `kida-templates>=0.2.7`
- `bengal-pounce>=0.2.2`
- `chirp-ui>=0.1.6` (optional, for `chirp[ui]`)

## [0.1.8] — 2026-03-10

### Changed

- **Version string** — Now derived from package metadata (single source of truth)

### Dependencies

- `chirp-ui>=0.1.5` (optional, for `chirp[ui]`)

## [0.1.7] — 2026-03-10

### Added

- **App shell guide** — Full documentation for persistent layouts: navigation model (explicit boost on sidebar links), rendering rule (`Page` with `page_block_name`), shell actions, `nav_link` for content links, and interactive shell gotchas (OOB with `hx-swap="none"`, SSE event naming, ContextVar loss, dual template blocks).
- **Islands examples** — `islands/`, `islands_shell/`, `islands_swap/`, and `oob_layout_chain/` examples. Islands inside app shells, islands in dynamically swapped content, and OOB layout chains with depth/nesting.
- **Breadcrumbs and sidebar OOB** — Boosted layout navigation now updates breadcrumbs and sidebar state via OOB swaps.
- **Alpine Focus plugin** — Injected when `alpine=True` for tray/modal overlay focus management. Modals/trays store auto-injected for Alpine apps.
- **Alpine macro improvements** — Dropdown and tabs macros use `x-ref`, `x-id`, focus return, and `$dispatch tab-changed` for better accessibility.
- **Kida integration docs** — Template integration guide and fragments reference.
- **`wizard_form` contract extraction** — Contract checker now extracts IDs from `wizard_form()` macro (fixes false-positive "unknown target" for wizard form containers).

### Changed

- **Shell-owned boost** — `app_shell_layout.html` puts `hx-boost="true"`, `hx-target="#main"`, `hx-swap="innerHTML"`, and `hx-select="#page-content"` on `<main id="main">` (with a `#page-content` wrapper inside). Links inside inherit SPA navigation automatically. Sidebar links (outside `#main`) carry their own attributes via `sidebar_link()`. Also adds `tabindex="-1"` for focus management, scroll-to-top on navigation, `overscroll-behavior: contain`, and a CSS-only loading indicator. `chirpui-transitions.css` scopes View Transitions to `#main` and suppresses VT on `.chirpui-fragment-island`.
- **HX-Reselect removal** — Fragment responses no longer send `HX-Reselect: *`; no longer needed with explicit boost on links.
- **Context provider module names** — `_context.py` files load with path-based names (`_chirp_ctx_collections`, `_chirp_ctx_settings`, etc.) instead of depth-based ones. Sibling directories no longer overwrite each other in `sys.modules`.
- **htmx debug targetError** — "Target Not Found" toast now includes remediation hint: co-locate target with mutating element when target is in a different fragment than the form.

### Fixed

- **Kanban board OOB/SSE** — Move/add/delete routes use empty main fragment so column and stats updates are OOB-wrapped. SSE adds OOB-aware template blocks (e.g. `column_block_oob`, `stats_block_oob`) with correct event naming for `sse-swap` listeners.
- **Wizard form contract** — Templates targeting `wizard_form` IDs no longer get false-positive "unknown target" warnings.

### Dependencies

- `kida-templates>=0.2.6`
- `chirp-ui>=0.1.4` (optional)
- `patitas>=0.3.5` (optional, for markdown)

## [0.1.6] — 2026-03-06

### Added

- **PageComposition API** — Python-first composition with `ViewRef`, `RegionUpdate`, and `PageComposition`. Explicit `fragment_block` / `page_block` semantics and region updates for shell actions. `Page` and `LayoutPage` are normalized through the same render-plan pipeline. See `chirp.templating.composition`.
- **Suspense + layout chain** — Handlers that return `Suspense` from `mount_pages` routes now receive the full layout shell (head, CSS, sidebar). `upgrade_result` wraps `Suspense` in `LayoutSuspense` when a layout chain exists; `render_suspense` wraps the first chunk via `render_with_layouts`. Fragment-only requests skip layout wrapping (same as `LayoutPage`). `layout_context` is merged into template context so cascade values (`shell_actions`, `current_user`) reach Suspense templates.
- **kanban_shell example** — Full example app with app shell, chirp-ui, mount_pages, OOB swaps, SSE, filter sidebar, and CRUD. Demonstrates `mount_pages` + `@app.route` mix.
- **htmx debug overlay** — S-tier debug panel with activity log, inspector, and swap flash when `config.debug=True`. Collapsible framework frames, Kida branding/version, ParseError suggestions.
- **HX-Reselect header** — Fragment responses now send `HX-Reselect: *` so htmx re-parses OOB swaps correctly when the response structure differs from the initial request.
- **Data layout patterns** — chirp-ui guide documents UI layout patterns for app shells and content regions.

### Changed

- **Shell-actions OOB** — Region updates for `#chirp-shell-actions` now use `hx-swap-oob="innerHTML"` instead of `"true"` to preserve container attributes (classes, structure) during boosted navigation.
- **Contracts** — `extract_mutation_target_ids()` uses `\baction\b` in regex to avoid false positives from `form_action`, `data-action`, etc.

### Fixed

- **TemplateNotFoundError** — Shell-actions OOB render catches `TemplateNotFoundError` when chirp-ui is not installed and falls back to empty OOB.

## [0.1.5] — 2026-03-04

### Fixed

- **chirp-ui filters** — `TemplateSyntaxError: Unknown filter 'html_attrs'` when using chirp-ui templates. `use_chirp_ui(app)` now auto-registers chirp-ui filters (`html_attrs`, `bem`, `field_errors`, `validate_variant`). `create_environment` adds env-level fallback when chirp-ui is installed, so filters are present even without explicit `register_filters`. See RFC 001 (component-filter-contract).

## [0.1.4] — 2026-03-04

### Added

- **Enterprise config** — `AppConfig.from_env()` loads config from environment (CHIRP_* vars). Optional `python-dotenv` via `pip install chirp[config]`. New fields: `env`, `redis_url`, `audit_sink`, `feature_flags`, `http_timeout`, `http_retries`, `skip_contract_checks`, `lazy_pages`
- **Health probes** — `chirp.health.liveness()`, `readiness(checks)`, `HealthCheck` for Kubernetes liveness/readiness probes
- **Request ID** — `Request.request_id` for request tracing
- **Structured logging** — `chirp.logging` module for JSON log format and lifecycle events
- **Pluggable session backends** — `SessionStore` protocol with `CookieSessionStore` and `RedisSessionStore`. `RateLimitBackend`, `LockoutBackend` protocols for auth middleware
- **Domain protocol** — `Domain` protocol and `register_domain()` for pluggable feature modules
- **Shell scaffolding** — `chirp new <name> --shell` scaffolds app with persistent shell (topbar + sidebar)
- **Layout slot context** — `LayoutPage` slot content inherits caller context; documented in server
- **form_get example** — New example demonstrating GET-based form search
- **Layout debug middleware** — `LayoutDebugMiddleware` for development
- **Resilience** — `chirp.resilience` with HTTP/DB timeout and retry docs; `Database` gains `connect_timeout`, `connect_retries`

### Changed

- **App architecture** — `app.py` split into `app/` package (compiler, lifecycle, registry, runtime, server, state, diagnostics)
- **Contracts** — `contracts.py` split into `contracts/` package with modular rules (htmx, forms, layout, SSE, islands, swap, etc.)
- **Lazy imports** — Top-level `chirp` uses lazy imports for faster startup
- **Kida errors** — ANSI escape codes stripped from Kida errors in HTTP/SSE/JSON responses
- **Session middleware** — Refactored for pluggable backends

### Fixed

- **Contracts** — Regex for Kida URL extraction in htmx attributes
- **Contracts** — Action+method matrix: GET default, swap safety for form actions

[0.3.3]: https://github.com/lbliii/chirp/releases/tag/v0.3.3
[0.3.2]: https://github.com/lbliii/chirp/releases/tag/v0.3.2
[0.3.1]: https://github.com/lbliii/chirp/releases/tag/v0.3.1
[0.3.0]: https://github.com/lbliii/chirp/releases/tag/v0.3.0
[0.1.8]: https://github.com/lbliii/chirp/releases/tag/v0.1.8
[0.1.9]: https://github.com/lbliii/chirp/releases/tag/v0.1.9
[0.2.0]: https://github.com/lbliii/chirp/releases/tag/v0.2.0
[0.1.7]: https://github.com/lbliii/chirp/releases/tag/v0.1.7
[0.1.6]: https://github.com/lbliii/chirp/releases/tag/v0.1.6
[0.1.5]: https://github.com/lbliii/chirp/releases/tag/v0.1.5
[0.1.4]: https://github.com/lbliii/chirp/releases/tag/v0.1.4

## [0.1.3] — 2026-03-03

(Release notes to be added)

[0.1.3]: https://github.com/lbliii/chirp/releases/tag/v0.1.3

## [0.1.2] — 2026-02-18

### Added

- **Islands (V1)** — Framework-agnostic contract for isolated high-state UI widgets:
  - Mount metadata: `data-island`, `data-island-props`, `data-island-src`, `data-island-version`, `data-island-primitive`
  - `app.check()` validates island mounts and primitive contracts
  - No-build primitive style: plain ES modules from `/static/islands/*.js` without a bundler
  - Runtime diagnostics and safety checks for props, version, and cross-reference
- **chirp-ui integration** — `chirp.ext.chirp_ui.use_chirp_ui(app)` registers chirp-ui static files (CSS, themes).
  Template loader auto-detects chirp-ui when installed. Optional `ui` extra: `pip install bengal-chirp[ui]`
- **Auth hardening** — Production-ready authentication and abuse protection:
  - `AuthRateLimitMiddleware` — Rate limit login/reset endpoints
  - `LoginLockout` — Lockout and backoff for repeated failures
  - `SecurityAudit` — Audit events for failures, lockouts, and blocked attempts
- **Alpine.js support** — `chirp/alpine.html` macros for `x-data`, `x-init`, reactive bindings.
  Server-side Alpine integration and `app.check()` validation for Alpine islands
- **LLM playground example** — New example app demonstrating streaming LLM chat with htmx
- **Documentation** — Guides for islands, auth hardening, Alpine + htmx, and no-build high-state

### Changed

- **Dependencies** — `kida-templates>=0.2.2` (was 0.2.1)
- **CI** — Ruff linting, prek pre-commit, GitHub Actions workflow
- **RAG demo** — Updated with chirp-ui integration

### Fixed

- Various test and type fixes across examples and core modules

[0.1.2]: https://github.com/lbliii/chirp/releases/tag/v0.1.2

## [0.1.1] — 2026-02-15

### Added

- **`chirp` CLI** — New console entry point with three subcommands:
  - `chirp new <name> [--minimal]` — Scaffold a project with app, templates, static assets,
    and tests. `--minimal` generates a single-file starter.
  - `chirp run <app> [--host HOST] [--port PORT]` — Start the dev server from an import
    string (e.g. `chirp run myapp:app`).
  - `chirp check <app>` — Validate hypermedia contracts from the command line.
- **`Template.inline()`** — Prototyping shortcut that renders a template from a string
  instead of a file. Returns an `InlineTemplate` instance that works through content
  negotiation without requiring a `template_dir`.
- **`InlineTemplate`** — New return type for string-based template rendering. Separate
  from `Template` so negotiation can distinguish it and `app.check()` can warn about
  inline templates in production routes.
- **Built-in template filters** — `field_errors` extracts validation messages for a single
  form field from an errors dict. `qs` builds URL query strings, automatically omitting
  falsy values. Both are auto-registered in the Kida environment at startup.
- **`form_or_errors()`** — Glue function that combines `form_from()` and `ValidationError`
  into a single call. Returns `T | ValidationError`, eliminating the try/except boilerplate
  for form binding errors.
- **`form_values()`** — Utility that converts a dataclass or mapping to `dict[str, str]` for
  template re-population when validation fails.
- **Form field macros** — Shipped in `chirp/forms.html`, importable via
  `{% from "chirp/forms.html" import text_field %}`. Five macros (`text_field`,
  `textarea_field`, `select_field`, `checkbox_field`, `hidden_field`) render labelled
  fields with inline error display using the `field_errors` filter.
- **Filesystem-based page routing** — Layout-nested page discovery from directory structure.
- **`app.provide()`** — Dependency injection for request-scoped context providers.
- **Reactive block pipeline** — Structured reactive templates with derived state.
- **SSE safety checks** — Contract validation for event streams and event cross-reference.
- **Safe target** — `hx-target` safety for event-driven htmx elements.
- **Security headers middleware** — HSTS, X-Content-Type-Options, etc.
- **View transitions** — OOB swap support for View Transitions API.
- **Production deployment** — Pounce Phase 5 & 6 support, deployment documentation.
- **Typed extraction** — Query/form/JSON extraction via dataclasses in handler signatures.

### Dependencies

- `kida-templates>=0.2.1` — Template engine
- `bengal-pounce>=0.2.0` — ASGI server

[0.1.1]: https://github.com/lbliii/chirp/releases/tag/v0.1.1

## [0.1.0] — 2026-02-09

Initial release of Chirp — a Python web framework for HTML-over-the-wire apps,
built for Python 3.14t with free-threading support.

### Added

#### Core Framework

- `App` — ASGI application with route registration, middleware pipeline, and
  lifecycle management
- `AppConfig` — Frozen configuration with sensible defaults
- Type-driven content negotiation: return strings, dicts, `Template`, `Fragment`,
  `Stream`, `EventStream`, `Response`, or `Redirect` from route handlers

#### Routing

- Decorator-based route registration with `@app.route(path)`
- Path parameters with type conversion (`/users/{id:int}`)
- Method dispatch (`GET`, `POST`, `PUT`, `DELETE`, etc.)
- Automatic `HEAD` and `OPTIONS` handling

#### Templates (Kida Integration)

- `Template(name, **ctx)` — Full-page Kida template rendering
- `Fragment(name, block, **ctx)` — Render named template blocks independently
  for htmx partial updates
- `Stream(name, **ctx)` — Progressive HTML streaming via Kida
- Auto-discovery of template directories

#### Real-Time

- `EventStream(generator)` — Server-Sent Events for real-time HTML updates
- SSE with Kida-rendered fragments for zero-JS real-time UI

#### HTTP

- Immutable `Request` with query params, headers, cookies, body parsing
- Chainable `Response` with `with_header()`, `with_cookie()` methods
- `Redirect` for HTTP redirects
- `form_from()` for typed form binding and validation

#### Middleware

- Protocol-based middleware (`async def mw(request, next) -> Response`)
- Built-in: CORS, StaticFiles, HTMLInject, Sessions
- `app.add_middleware()` for composable request/response pipelines

#### Security

- Session middleware with signed cookies (via itsdangerous)
- `login()`, `logout()`, `get_user()` authentication helpers
- `@login_required` and `@requires()` authorization decorators
- `is_safe_url()` for open redirect protection

#### Data

- `Database` — Typed async database access (SQLite via aiosqlite, PostgreSQL
  via asyncpg)

#### AI

- `LLM` — Provider-agnostic LLM streaming via raw HTTP
- `ToolCallEvent` for structured tool calling

#### Testing

- `TestClient` — HTTPX-based test client for isolated route testing

#### Developer Experience

- `app.run()` — Built-in development server via Pounce
- `app.check()` — Compile-time validation of the full hypermedia surface
  (routes, template refs, fragment blocks)
- `py.typed` PEP 561 marker for type checker support
- Free-threading declaration (`_Py_mod_gil = 0`)

### Dependencies

- `kida-templates>=0.1.2` — Template engine
- `anyio>=4.0` — Async runtime
- `bengal-pounce>=0.1.0` — ASGI server

[0.1.0]: https://github.com/lbliii/chirp/releases/tag/v0.1.0

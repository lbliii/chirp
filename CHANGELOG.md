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

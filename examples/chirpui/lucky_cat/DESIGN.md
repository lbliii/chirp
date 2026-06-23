# Lucky Cat — Design Doctrine

> The flagship ChirpUI app-shell example. A deterministic, simulated maneki-neko
> **trading-floor UI** — the kind of product surface crypto/web3 teams ship, but
> deliberately *not* wired to chain or exchange infrastructure — that composes
> *over* chirp-ui instead of forking it, and runs honestly on Python 3.14
> free-threading.

This is the teaching artifact for the example: what it is, the hard-won
information-architecture doctrine, the feature map, the patterns worth stealing,
the two standing footguns, and the design tokens. Everything below is grounded
in the code in this directory — file, route, macro, and store names are real.

---

## 1. What it is

Lucky Cat is a playful "lucky cat casino" trading floor: a topbar with a live
cross-page ticker strip, a $MEOW house-token balance and a notifications bell; a
two-tier navigation rail; a curated Markets Home lobby (with Trending, Research,
and a Favorites view as the other fixed Markets destinations); a market-detail
page with a gradient area chart, an order book, and a trade tape; a trade flow; a
Suspense portfolio dashboard; a watchlist; and a Cmd-K command palette. **Browsing the market data
is open to everyone; the account section and every mutation are gated behind
session sign-in** — the auth showcase that exercises all three gating levels (§8).

It is **not** wired to a real exchange. `feed.py` defines a source-agnostic
`FeedSource` protocol and ships one implementation, `SimFeed` — a fully
deterministic, dependency-free price engine. Same seed (`DEFAULT_SEED = 0xCA7`)
=> identical tick sequence, so the sim doubles as the test fixture and lets the
example clone-and-run offline and CI-safe. Opt-in live adapters (Kraken WS,
CoinGecko REST, mempool.space on-chain panel) sit behind ``LUCKY_CAT_FEED`` and
fall back to ``SimFeed`` when deps or upstream endpoints are unavailable.

### Web3 non-goals (deliberately out of scope)

Lucky Cat teaches ChirpUI and server-owned realtime — not blockchain plumbing.
These are **not** on the roadmap for this example:

- **No wallet-connect** — sign-in is session-based (`AuthMiddleware` + demo
  account), not a browser wallet or SIWE flow.
- **No on-chain settlement** — the `$MEOW` balance and fills live in in-memory
  Python stores (`wallet.py`, `trade_store.py`), not a ledger or smart contract.
- **No matching engine** — orders validate and fill against the sim price +
  in-memory book logic; there is no order-matching service, mempool, or CLOB
  adapter.

The visual language (tickers, order book, tape, portfolio) mirrors a trading-floor
product UI so prospects can evaluate Chirp on familiar chrome. The simulation
boundary is the point: deterministic, offline, CI-safe, and free of external
services.

Three things make it the flagship:

- It **composes over chirp-ui** (`use_chirp_ui(app)` + mounted filesystem
  pages). It does *not* fork the package, touch `src/chirp`, or add a framework
  feature. The look is a `--lc-*` token layer that re-points chirp-ui's own
  `--chirpui-*` chrome vars (see §6).
- It is **secure by default** and `app.check()`-ERROR-free. The
  Session → CSRF → SecurityHeaders stack is wired in `app.py` before the
  mutating routes, with a chirp-ui-compatible CSP (`_CHIRP_UI_CSP`).
- It is an **honest free-threading demo.** `SimFeed` fans every per-tick price
  update across a `ThreadPoolExecutor` (genuine CPU-bound parallelism, no
  `sleep()` fakery), and every piece of shared mutable state lives behind a
  `threading.Lock` (see §4). The `/ft/stream` route reports real ticks/sec —
  high on a `python3.14t` (GIL-disabled) build, GIL-bound otherwise. The
  parallelism is *threads within one process*: the app pins `workers=1` because
  ALL its state — wallet, trade store, notifications log, the SimFeed, AND the
  signal bus behind `@app.signal` — is in process memory, and the one
  `/_chirp/live` signal connection is pinned to a single worker. See §7.

Run it (always `uv run`; a bare interpreter may have a stale kida):

```bash
PYTHONPATH=src uv run python examples/chirpui/lucky_cat/app.py
```

---

## 2. The IA doctrine (read this twice)

The information architecture is the single most opinionated thing in the
example, and it was hard-won. There are **four tiers**, and there is a crisp,
prescriptive rule for what goes where. When you add a feature, decide its tier
*first*.

| Tier | What lives here | Owned by |
|------|-----------------|----------|
| **Topbar** | Identity + **global** state + **global** actions | `_layout.html` blocks (`brand_link`, `topbar_center`, `topbar_end`) + `_context.py` `ShellActions` |
| **Outer icon rail** | The top-level **rooms** (persistent everywhere) | `navigation._PRIMARY_ROOMS` → `primary_icon_rail` |
| **Inner contextual rail** | **Route-context** sections (change per room), incl. the Watchlist filter lane | `navigation.shell_navigation()` → `inner_sidebar_shell` |
| **Inner page** | The actual content | `pages/**/page.html` `page_content` block |

### The rule

- **Topbar = identity + global state + global actions, nothing else.**
  - Identity: the Lucky Cat brand. Global state: the live ticker strip
    (`#lucky-cat-ticker`, the `ticker` signal sink), the `$MEOW` balance (a bare
    `{{ signal('balance') }}` sink — no DOM id, it carries no OOB twin anymore),
    the notifications bell (`#notif-badge`, a `notif_badge` derived-signal sink).
    Global actions: Deposit $MEOW (primary), the theme toggle, the Cmd-K palette
    trigger, the "More" overflow.
  - **Identity is auth-aware** (§8): the topbar shows a "Sign in" link when
    anonymous and the user chip + a Sign-out form when signed in. The global state
    + global actions that are account-specific (the `$MEOW` balance, the bell, the
    Deposit action) render only when `current_user().is_authenticated` — the
    public ticker, theme toggle, and Cmd-K stay for everyone.
  - **Section navigation does NOT go in the topbar.** `_context.py` makes this
    explicit: there is deliberately **no `controls` zone** — "section navigation
    (Markets, etc.) belongs in the outer icon rail, NOT the topbar." The only
    topbar `ShellAction`s are `deposit` (primary, a global account action) and
    `docs`/About (overflow).
- **Outer icon rail = top-level rooms.** Markets / Portfolio / Trade / Activity
  / Settings, persistent on every page, icon-only. This is the *only* place a
  top-level destination lives. It never changes between routes.
- **Inner contextual rail = where you are.** `shell_navigation()` dispatches on
  `route_state.active_room` to build typed `NavSection`/`NavItem` trees; empty
  sections are pruned so the rail never shows a bare header. The Markets room is
  the **four fixed destinations** — **Home** (`/`), **Favorites**
  (`/markets/favorites`, the starred-only view + a live count badge), **Trending**
  (`/markets/trending`), **Research** (`/markets/research`) — *not* an O(N)
  one-row-per-market list (the full catalog lives only in Research). A coin-detail
  route PINS the current coin at the top of the rail (a single active lane with
  its 24h-change badge); the dead Overview/Order-book/Trades/Info jump anchors
  were removed (#282).
- **Inner page = content.** Everything route-specific.

### Two corollaries that fell out of the doctrine

- **`$MEOW` balance lives once, in the topbar.** `inner_sidebar_shell` has a
  pointed comment: "No footer balance here: the $MEOW balance is GLOBAL account
  state, so it lives once in the topbar (IA doctrine). Duplicating it in the
  rail also overflowed the column."
- **Favorites (`/markets/favorites`) is a Markets-room destination,** not its own
  room. `RouteState.active_room` keeps the Markets icon lit on the whole
  `/markets` tree and shows the fixed Markets rail with the Favorites destination
  active — a starred-only view of the same markets, not a new top-level place. A
  `RESERVED_MARKET_SEGMENTS` guard in `RouteState.market_detail_active` stops the
  fixed `/markets/{favorites,trending,research}` views from being mistaken for a
  coin detail route.

`RouteState` is the crown jewel: a frozen, queryless snapshot of the current
path with path-prefix `*_active` properties. Server-computed active state
(`aria-current="page"` + the active class) must stay consistent with the
app-shell layout's client `syncNav()`, which uses the same
`path == href or path.startswith(href + "/")` rule.

---

## 3. Feature map

Each feature, the Chirp **return type** it leans on, and the chirp-ui pieces it
composes. (Note: this example uses `Page` / `Fragment` / `OOB` / `FormAction` /
`ValidationError` / `Suspense` / `EventStream`. It does **not** use `Stream` —
the progressive-first-paint type — because Suspense's shell-first model is the
right fit for the slow dashboard.)

| Feature | Route(s) | Return type | chirp-ui / composition |
|---------|----------|-------------|------------------------|
| **Markets Home (lobby)** | `GET /markets` (`pages/markets/page.py`) + `GET /` alias (`pages/page.py`) | `Page` | the curated, BOUNDED lobby (#281): a stat strip (`ranking.market_stats`), a top-movers preview (`ranking.top_gainers/losers/volume`, a few each, as links into Trending), a watchlist preview + a featured market (`market_card`), and a CTA into Research. `/` is an ALIAS (no redirect) rendering the SAME `markets/page.html` from the shared `lobby.lobby_context`. The old full grid is RETIRED — the full catalog lives only in Research. **De-dupe footgun:** the featured symbol is dropped from the watchlist preview so `#luckycat-card-{symbol}` / `#watchlist-star-{symbol}` never duplicate (also the unstar-prune target). |
| **Trending** | `GET /markets/trending` (`?seg=gainers/losers/volume`) | `Page` / `Fragment` (`movers_region`) | leaderboard of `ranking.top_gainers/losers/volume` over `research.build_rows` (PR4 seam); segmented control swaps `#movers-region`; **snapshot-per-swap**, no live re-rank; the swap is routed off `HX-Target` so a boosted full-page nav still renders the shell |
| **Research** | `GET /markets/research` (`?q=&sort=&dir=&page=&sector=` + price/change/vol band keys + `cmp`) | `Page` / `Fragment` (`research_results`) | the power surface for 500+ coins: search (`search.matches`) + facet filters + sortable column headers + **server-side pagination** + a lightweight server-rendered compare tray, all over `research.query_catalog` (PR4 seam, filter→stable-sort→slice); URL-param-driven, so every control's `hx-get` is a precomputed `research_url` querystring; each control swaps `#research-results` (routed off `HX-Target`) |
| **Market detail** | `GET /markets/{symbol}` | `Page` | gradient area chart (`HeroChart` geometry, no JS chart lib) + order book + trade tape; full-page blocks twinned with `*_oob` |
| **— chart timeframe toggle** | `GET /markets/{symbol}/chart?tf=` (`referenced=True`) | `Fragment` (`chart_region`) | segmented 1m/1H/1D/1W toggle; `tf` clamped to `feed.INTERVALS` |
| **— live ticker/book/tape** | `GET /markets/{symbol}/stream` (`referenced=True`) | `EventStream` | `sse_scope()`; yields the detail blocks `market_ticker_oob`/`order_book_oob`/`trade_tape_oob` (does **not** drive the topbar strip — that has one global owner) |
| **Topbar live ticker** | the `ticker` SIGNAL (source) on `/_chirp/live` | live signal | a rotating market spotlight (~2.5s) bound via `signal_block('ticker')` inside `#lucky-cat-ticker` on **every** page (sole owner of the strip, so no two-source flicker) |
| **Topbar $MEOW balance** | the `balance` SIGNAL (push) on `/_chirp/live` | live signal | `signal('balance')` in the topbar token AND the deposit modal; `/deposit` + `/trade` call `app.emit('balance', …)` so both homes swap in lockstep |
| **Trade (spot)** | `POST /trade/order` | `ValidationError` (422) **or** `FormAction` | multi-target OOB: `positions_oob` + `open_order_count_oob` + `toast`; the balance rides the `balance` signal (`app.emit`), a fill emits the `notifications` signal too |
| **— cancel** | `POST /trade/order/{id}/cancel` | `FormAction` | per-row `hx-swap="delete"` + count OOB; last-order empties `orders_table_oob` |
| **— convert** | `POST /trade/convert` | `Fragment` (422, htmx) / `FormAction` | self-contained: re-renders `#convert-form`, not the spot form |
| **Deposit** | `POST /deposit` | empty 204 | chirp-ui modal via `data-action="deposit"`; emits the `balance` signal (topbar + modal swap) and the `notifications` signal (bell reacts) |
| **Favorites** | `POST /watchlist/toggle` | `OOB` (star twin + count twin) | per-card / detail star `<button>`; `GET /markets/favorites` is a `Page` reusing `market_grid` (the starred-only view; moved from `/watchlist`, #282 — the POST route keeps its `watchlist.toggle` name) |
| **Notifications bell** | `POST /notifications/read` + the `notifications` SIGNAL (source) on `/_chirp/live` | empty 204 / live signals | chirp-ui `chirpuiDropdown()`; open-marks-read emits the signal so the **derived** `notif_badge` / `notif_announce` clear; the source generator drains the log + raises price alerts and emits the recent list (the dropdown re-renders over the **one** connection — the N→1 fold) |
| **Command palette (Cmd-K)** | `GET /search` (`referenced=True`) | `Fragment` (`palette_results_body`) | chirp-ui `command_palette` (`<dialog>` + `chirpuiDialogTarget`); `command_palette.palette_results` filters markets + rooms |
| **Mobile drawer nav** | (no route — shell chrome) | n/a | chirp-ui `drawer` + `chirpuiDialogTarget`; `mobile_drawer_nav` reuses the same `shell_navigation` model as the rail |
| **Collapsible rail** | (no route — cookie-persisted) | n/a | `shell.rail_is_collapsed()` read server-side for no-FOUC first paint; `static/lucky-cat-shell.js` drives the collapse toggle |
| **Suspense dashboard** | `GET /portfolio` | `Suspense` | shell-first; six deferred panels stream as OOB swaps from `trade_store` |
| **Free-threading proof** | `GET /ft/stream` (`referenced=True`) | `EventStream` | OOB-swaps a live ticks/sec figure into `#ft-panel` |
| **Sign in** | `GET` / `POST /login` (`pages/login/`) | `Page` / `ValidationError` (422) | prefilled demo card; bad creds re-render `login_form` in place, good creds `login()` + `FormAction` (HX-Redirect → full reload) |
| **Sign out** | `POST /logout` | `FormAction` | `logout()` (session regenerated) → HX-Redirect full reload home |
| **Account gating** | the gated `page.py` `get()` handlers | `@login_required` | anonymous → 302 `/login?next=`; `current_user()` swaps the topbar chrome + the `watchlist_star` (§8) |

`referenced=True` on the non-`<a href>` routes (search, all SSE streams, the
chart fragment) keeps `app.check()`'s orphan-route rule quiet and the
`test_links` crawl from visiting them.

---

## 3.5 Where code lives

After the Wave 2 split (#404 / #406), the teaching layout is:

| Layer | Location | What |
|-------|----------|------|
| **Bootstrap** | `app.py` (~30 lines) | `mount_pages`, import wiring |
| **Wiring** | `wiring/app_factory.py` | App config, `emit_signal`, ChirpUI registration |
| | `wiring/middleware.py` | Session → Auth → CSRF → security headers |
| | `wiring/signals.py` | `@app.signal` / `@app.derived` (freeze-before-mount) |
| | `wiring/routes/` | SSE / EventStream + layout-global POST (`/logout`, `/notifications/read`, `/watchlist/toggle`) |
| **Pages (GET)** | `pages/**/page.py` | Filesystem routes — `Page`, `Suspense`, … |
| **Mutations (POST)** | `pages/**/_actions.py` | POST-to-self via `_action` field (`contacts_shell` pattern) |
| **Domain** | `feed.py`, `trade_store.py`, … | Simulated stores — no Chirp imports upward |

Trade example: `pages/trade/_actions.py` `@action("order")` handles
`POST /trade`; deposit lives in `pages/markets/_actions.py`; cancel in
`pages/portfolio/orders/_actions.py`. Shell-global mutations that fire from
every page (`/logout`, bell read, star toggle) stay in `wiring/routes/` because
they are not colocated with one page tree.

Stale-module purge for shared pytest workers lives in `wiring/bootstrap.py`
(conftest calls it — **not** in `app.py`).

---

## 4. Patterns worth stealing

### The kanban `*_oob` twin idiom

A region that updates out-of-band needs **two** declarations, and they share one
single-source-of-truth body macro so the markup can never drift:

1. A **`{% region %}`** declared *top-level* in the template. `app.check()`'s
   `oob_registry` rule discovers it by name (and `build_layout_contract` wires
   its `depends_on`). The region body carries **no** wrapper — the full-page
   layout supplies the wrapping element with the DOM id.
2. A **`{% fragment %}`** swap twin that **bakes its own `id` + `hx-swap-oob`**.
   `render_fragment()` emits a block verbatim with no OOB wrapping, so the
   fragment must include the same DOM id as the layout wrapper for the innerHTML
   (or outerHTML) swap to land.

Live example in `_layout.html`:

- `watchlist_count_oob` + `watchlist_count_swap` (`#watchlist-count`), body =
  `watchlist_count_body` (imported from `_components/sidebar.html`).

The cross-page chrome that *used* to use this idiom has migrated to live
**signals** on the one `/_chirp/live` connection — the ticker (`ticker`), the
balance (`balance`), and the notifications bell (`notifications` source +
`notif_badge` / `notif_announce` derived) — so their OOB regions/twins are gone.
The bell's signal sinks are EXISTING elements with manual `sse-swap` attributes
(`#notif-list` / `#notif-badge` / `#notif-announce`), not `signal_block()`.

One OOB region is registered in `app.py`: `watchlist_count_oob`
(`swap="innerHTML"`, `wrap=False` — the twin bakes its own wrapper, so the OOB
framework emits it verbatim instead of double-wrapping). The detail-page
`market_ticker_oob`/`order_book_oob`/`trade_tape_oob` blocks bake their own
wrappers and need no registration.

### `shell_outlet_attrs()` — the boosted contract

Every nav link (icon rail, inner rail, drawer, brand) carries
`{{ shell_outlet_attrs() }}` (from `chirpui/shell_frame.html`): target `#main`,
swap `innerHTML`, select `#page-content`, plus `hx-sync="#main:replace"` so
rapid nav clicks coalesce. This is the boosted shell — a click swaps only
`#page-content` into `#main`, never a full reload. On boosted nav the single
`sidebar_oob` region re-renders **both** rails in one swap (chirp-ui auto-wraps
it into `<div id="chirpui-sidebar-nav" hx-swap-oob="innerHTML">`), so the active
room and contextual sections recompute from `current_path`.

The catch is footgun #2 (§5): anything inside `#main` that does a *local* swap
inherits this outlet and must override it on itself.

### SSE / Suspense / Stream — pick the right one

Canonical decision tree (site):
[[docs/build-apps/streaming-updates/realtime-decision-tree|Realtime decision tree]]
— when to use each mechanism and which Lucky Cat feature uses which.

- **`EventStream` + `sse_scope()`** for *page-specific* live updates after the
  page loads: the per-market `/markets/{symbol}/stream` (detail page only) and
  `/ft/stream` (the portfolio free-threading proof panel).
- **Live signals on the one `/_chirp/live` connection** for cross-page chrome:
  `balance` + `ticker` + the notifications bell are all signals fanned out over a
  single persistent connection opened by `signal_connect()` in the shell. The
  bell is the N→1 showcase: a SOURCE signal (`notifications`) drains the log +
  raises price alerts and emits a `NotifFeed` snapshot (the recent rows AND the
  unread count, captured atomically), and two DERIVED signals (`notif_badge`,
  `notif_announce`) recompute PURELY from `feed.unread` in the same emit cascade.
  This is the pure-derived contract: a derived reads only its INPUT SIGNAL
  VALUES, never a process-local store (so it is deterministic across workers and
  race-free across threads) — which is why the count travels inside the signal
  value rather than being re-read from the notifications store. The bell's sinks
  are EXISTING elements (`#notif-list`,
  `#notif-badge`, `#notif-announce`) carrying manual `sse-swap` attributes — not
  `signal_block()` (which would inject its own wrapper). Result: every page holds
  exactly one persistent shell connection (plus the page-specific stream above
  where present), replacing the old separate `/notifications/stream` scope.
- **`Suspense`** for a one-shot slow page: `/portfolio`. The shell paints
  instantly with skeletons, then six awaitable panels stream in as OOB swaps as
  they resolve from `trade_store` (each store read is wrapped in
  `asyncio.to_thread` so it is a genuine awaitable). Loading-vs-loaded uses
  **`{% if x is deferred %}`** (the value is the `DEFERRED` sentinel, *not*
  `None`) — `is not none` would mis-branch and an empty resolved tuple would
  stick on a skeleton. `defer_blocks` bypasses static discovery (several
  deferred keys appear only inside chirp-ui macro args) and `defer_map` remaps
  block names to section DOM ids (`portfolio_value` → `portfolio-value`, etc.)
  so each OOB swap lands fail-loud on a real id.
- **`Stream`** (progressive section-by-section first paint) is the *third*
  option and is intentionally **not** used here — a slow dashboard wants
  shell-first (Suspense), not a deferred first byte.

### The deterministic feed

`SimFeed` is the demo's spine. Determinism + parallelism coexist because **each
symbol owns an independent, seeded `random.Random` stream**, so advancing one
symbol never depends on the order symbols are advanced — which is exactly what
lets `_advance_all` fan out across the worker pool without perturbing the
sequence. Symbol seeds derive from the master seed via `zlib.crc32` (`_sym_hash`)
— *not* builtin `hash()`, which is salted per process (`PYTHONHASHSEED`) and
would break the "same seed => identical sequence" guarantee across runs. The
feed `warm()`s on build so the first paint shows populated tape/candles/24h
stats. Coarse-interval candles (1H/1D/1W) are a per-`(symbol, interval)`-seeded
synthetic walk **affine-mapped** so `closes[0] == open_24h` and
`closes[-1] == live price` — pinning both endpoints so the chart's
first-vs-last direction can never contradict the 24h delta pill.

`test_feed_determinism.py` (`TestSimFeedGoldenSnapshot`) is the *pinning* layer
on top of the relational tests in `test_app.py`: it freezes the **exact** warmed
numbers (the full 6-symbol ticker dict, 1H/1D/1W candle lengths + pinned
endpoints, the 2-candle 1m live ring, the depth-3 book, the top-3 tape, and the
sparkline/hero-chart geometry) at `seed=0xCA7` after `reset()` + `warm()` (24
steps). It constructs its *own* `SimFeed` and calls both `reset()` (the instance
method is a **pure** step-0 restore — it does *not* warm) **and** `warm()`
explicitly; it never touches the `get_feed()` singleton (shared mutable state).
Asserting `ts == 24.0` locks `_WARM_STEPS`. Any reversion of `_sym_hash` to
builtin `hash()`, any dict-order change, or any fan-out nondeterminism flips a
literal and fails the snapshot — that is the regression class it guards.

### Thread-safe stores (free-threading)

Every store follows one convention: frozen-dataclass models, module-level
mutable state behind a single `threading.Lock`, immutable snapshots out, and a
`reset()` for test isolation (all wired into `conftest.py`).

- `wallet.py` — `$MEOW` balance + deposit ledger; `debit()` refuses to go
  negative.
- `trade_store.py` — the race-safe heart. `try_place_order` re-checks the
  balance **and** debits the wallet inside *one* lock, so two concurrent buys
  racing the same balance can never both win; the loser gets a clean 422, never
  an unhandled `ValueError` 500. Lock ordering is documented: prices are
  snapshotted *before* `_lock` (so `feed._lock` is never held across `_lock`),
  and `wallet._lock` is only ever taken *inside* `_lock`.
- `watchlist.py` — starred set under one lock; `toggle()` flips atomically and
  returns the new state, so the rendered star and the rail count can't drift.
- `notifications.py` — one log + id counter + read watermark under one lock;
  `add` is the single append path so the badge count can't drift from the rows.
- `feed.py` — engine state under `_lock`; an independent `_tick_lock` guards the
  observability-only tick counter so the FT panel's hot path never touches the
  engine lock (and the counter never perturbs the deterministic sequence).

---

## 5. The two standing footguns

These bit the example during development. Do not regress them.

### Footgun #1 — nested interactive

**Symptom:** a control *inside* a full-card `<a>` (or inside the brand `<a>`)
either hijacks navigation or is invalid HTML — clicking the star navigated to
the market instead of toggling; the mobile hamburger inside the brand anchor
navigated home instead of opening the drawer.

**Fix:** interactive controls must be **siblings** of the anchor, never
descendants.

- The watchlist star and the market card `<a href="/markets/{symbol}">` are
  siblings inside a `position:relative` `.luckycat-market-card-cell` wrapper; the
  star is absolutely positioned over a corner via CSS
  (`_components/market.html`, `market_card`).
- The mobile hamburger sits as a sibling **before** the brand anchor; the brand
  markup goes inside `shell_brand_link` via `{% call %}` (`_layout.html`,
  `brand_link` block). chirp-ui renders the brand block *inside* the `<a>`, so a
  `<button>` there would bubble its click to the anchor.

#### Corollary — the Home-lobby duplicate-id de-dupe (#281)

The market card bakes a per-symbol `#luckycat-card-{symbol}` cell id + a
`#watchlist-star-{symbol}` star id (the OOB-swap / unstar-prune targets). The Home
lobby renders cards in **two** regions — the featured slot and the watchlist
preview — so a coin in both would render those ids **twice**: invalid HTML that
breaks `getElementById` AND the `/watchlist/toggle` `hx-swap-oob="delete"` prune
(it would match two `#luckycat-card-{symbol}` cells). `lobby.lobby_context`
**de-dupes at render** — the featured symbol is dropped from the watchlist preview,
and the movers preview is rendered as coin-detail *links* (never `market_card`), so
it carries no card/star ids at all. Pinned by `test_lobby.py` (the
starred-featured-coin proof) + `test_app.py::TestLanding`.

### Footgun #2 — boosted-shell `hx-select`

**Symptom:** any local-swap or OOB control inside `#main` inherits the boosted
outlet (`hx-target=#main`, `hx-select=#page-content`) from its ancestors. When
the response *doesn't* contain `#page-content`, htmx swaps **empty** and the
control's region vanishes — the convert form disappeared; the star toggle
churned the whole page.

**Fix:** the control must **override the inherited outlet on itself** with an
`hx-select` of its *own* fragment id (and usually `hx-swap="none"` when it only
needs OOB swaps). `hx-disinherit` is the **wrong lever** — it only affects
*descendants*, not self-inheritance.

- Watchlist star (`_components/market.html`, `watchlist_star`):
  `hx-swap="none"` + `hx-select="#watchlist-star-{symbol}"`, so `#main` never
  churns and the two baked OOB twins apply via the `hx-swap-oob` scan.
- Convert form (`pages/trade/convert/page.html`): `hx-target="#convert-form"` +
  `hx-swap="outerHTML"` + `hx-select="#convert-form"`, so a 422 re-renders the
  form in place instead of swapping empty.
- Chart timeframe toggle (`/markets/{symbol}/chart`): each button overrides with
  `hx-target="#market-chart"` + `hx-swap="outerHTML"` + `hx-select="#market-chart"`.
- Trending segment toggle (`pages/markets/trending/page.html`): each button
  overrides with `hx-target="#movers-region"` + `hx-swap="outerHTML"` +
  `hx-select="#movers-region"`, and `page.py` re-emits the `movers_region` block
  (routed off `HX-Target`) so the swap finds its own wrapper.
- Research controls (`pages/markets/research/page.html`): the search box, every
  facet chip, every sortable column header, the pager, and the compare pin/unpin
  links **all** override with `hx-target="#research-results"` +
  `hx-swap="outerHTML"` + `hx-select="#research-results"` (via the one
  `results_swap()` macro so the trio can't drift), and `page.py` re-emits the
  `research_results` block (routed off `HX-Target`) so each swap finds its own
  wrapper.
- Notifications bell trigger (`_layout.html`): `hx-target="#notif-badge"` +
  `hx-swap="none"` + `hx-select="#notif-badge"`.

---

## 6. Design tokens

The strategy is a **polish layer over chirp-ui, not a fork.** `_layout.html`
`head_extra` declares a product token layer (`--lc-*`) and then re-points
chirp-ui's own `--chirpui-*` chrome vars at it, so every chirp-ui component
(cards, buttons, sidebar, modals, fields) inherits the new look — depth over
flat borders — for free. Dark-first (crypto default) under `:root`, with an
intentional light theme under `[data-theme="light"]` and the
`prefers-color-scheme` media query. The inline `<style>` carries
`nonce="{{ csp_nonce() }}"`; the bulk of component CSS lives in
`static/lucky-cat.css`.

### Palette

| Token | Value (dark) | Meaning |
|-------|--------------|---------|
| `--lc-jade` | `#2fd49a` | signature accent + market **up** |
| `--lc-red` | `#ff5a6a` | market **down** + danger |
| `--lc-gold` | `#f5b13d` | `$MEOW` / brand coin accent |
| `--lc-up` / `--lc-down` | `var(--lc-jade)` / `var(--lc-red)` | directional semantics, mapped everywhere |

### Surface planes (depth, not borders)

`--lc-plane-base` (`#0e0f12`, page floor) → `--lc-plane-surface` (`#16181d`,
card) → `--lc-plane-raised` (`#1e2128`, hovered) → `--lc-plane-overlay`
(`#262a33`, menus/modals), divided by near-borderless `--lc-hairline`. The
single biggest anti-wireframe move is the elevation ramp: `--lc-elevation-1`
through `--lc-elevation-3` + `--lc-elevation-pop`, plus accent glows
(`--lc-glow-jade` / `--lc-glow-gold`).

### Type

- **Geist Variable** sans (`--lc-font-sans`) for UI and big numerals.
- **Geist Mono Variable** (`--lc-font-mono`) for monospace.
- `font-variant-numeric: tabular-nums` everywhere a figure can change width
  (prices, balances, ticker, order book, tape, positions) so numbers don't
  jitter.
- A confident scale: `--lc-text-xs … --lc-display-lg`, with tight tracking on
  big numerals (`--lc-tracking-display`).

### Motion

Motion tokens (`--lc-motion-instant … --lc-motion-slow`, `--lc-flash-duration`
price-tick pulse, `--lc-shimmer-duration` skeleton sweep, `--lc-lift` card
hover, `--lc-press` button press) **all** have a `prefers-reduced-motion: reduce`
floor in `static/lucky-cat.css` — any new animation must keep that floor.

### No-FOUC first paint

The cookie-backed rail collapse preference (`rail_is_collapsed()` in `shell.py`)
is read server-side and emitted into a nonced `#luckycat-rail-cookie-state`
`<style>` so the first paint already reflects the persisted collapsed state — no
flash-of-uncollapsed-rail. Collapse is a click-toggle, not a continuous
drag-resizer: a first-class resizable rail belongs in the chirp-ui peer package
(see #231's locked decision and `plan/completed/231-rail-collapse-resolution.md`).

---

## 7. The live-signal model + why `workers=1`

The cross-page chrome runs on Chirp's `signal()` primitive — a server-owned
reactive value pushed over **ONE** merged `/_chirp/live` SSE connection
(declare-once / bind-many). The shell's `signal_connect()` opens that single
connection on every page; the framework merges every registered topic onto it,
so a page holds exactly one persistent signal connection (plus the page-specific
`/markets/{symbol}/stream` on the detail page).

The three producer flavors, all live here:

- **PUSH** (`@app.signal('balance')` with no source) — a route imperatively
  `app.emit('balance', value)`s and every binding swaps. The decorated generator
  yields nothing.
- **SOURCE** (`@app.signal('ticker' | 'notifications')`) — an async generator
  that yields values as it walks the feed; the framework pumps it once per
  process and routes each yield through the same `emit()` path.
- **DERIVED** (`@app.derived('notif_badge' | 'notif_announce', on=('notifications',))`)
  — recomputes from its input signal's value and re-emits to its own bindings in
  the SAME emit cascade, for **both** `app.emit()` and the source-generator path.

### The pure-derived contract (multi-worker correctness)

A `derived` **must be a pure function of its input signal values** — it may never
read external/process-local mutable state. Reading a store inside a derived is
non-deterministic across workers (each worker holds a separate store copy) and
races the watermark across threads (the source-pump thread vs. the route thread),
so the emitted value can disagree with the data it was derived alongside. This is
why `notif_badge`/`notif_announce` read `feed.unread` straight off the emitted
`NotifFeed` rather than calling `notifications.unread_count()`: the source emits a
`snapshot()` that captures the rows AND the unread count atomically under one
lock, and the deriveds compute purely from that value. (The same anti-pattern
forced an earlier `net_worth` derived to be dropped — it had to read the trade
store.) When you add a derived, make its source signal's value carry everything
the derived needs.

### Why `workers=1` (default today — scale via the backplane seam)

The example pins `workers=1` in `app.py` (overriding the CPU-count default). That
is the **single-process default** for an in-memory demo, not a framework
limitation. Two compounding reasons make multi-process unsafe *without* a shared
backplane:

1. **All state is in process memory** — the wallet, trade store, notifications
   log, the SimFeed, AND the signal bus (the reactive bus behind `@app.signal`).
   Multiple OS-process workers would each hold a SEPARATE copy, so a deposit on
   one worker would be invisible to a request served by the next.
2. **The `/_chirp/live` connection is pinned to one worker.** With >1 worker, a
   page load that lands on a worker whose event loop is tied up serving a
   long-lived signal connection stalls — the "white screen" / freeze.

Scaling is a **one-class swap**, not an out-of-scope rewrite. Lucky Cat routes
mutations through `backplane.get_backplane().publish(name, value)` instead of
calling `app.emit` directly. The shipped default is `InProcessBackplane` (wraps
`App.emit` — today's behavior). For `workers>1`, implement the
`SignalBackplane` protocol with a shared bus (`RedisBackplane` is stubbed in
`backplane.py` with wiring notes) **and** move wallet/trade/notifications into
an external store — the backplane carries fan-out notifications, not
source-of-truth state. See the signal RFC for the full production path.

Keep this example at `workers=1` until both pieces are configured. The pure-derived
contract above is the discipline that keeps derived signals correct once events
cross process boundaries.

---

## 8. Auth & the three gating levels

Lucky Cat is **public-browse / gated-trading**, and it deliberately exercises the
WHOLE range of Chirp's auth surface rather than one blanket lock. Decide a new
surface's gating the way you decide its IA tier (§2): is it *market data* (public)
or *the account* (gated), and is the gate a *page*, a *component*, or an *action*?

| Level | Mechanism | Where |
|-------|-----------|-------|
| **Full-page** | `@login_required` on the `page.py` `get()` handler | the account rooms — `/trade`(+convert), `/portfolio`(+orders/history), `/activity`(+deposits/trades), `/markets/favorites`, `/settings`(+security/display). Anonymous → **302 `/login?next=<path>`** |
| **Component** | `current_user()` conditional in the template | the topbar ("Sign in" ↔ user chip + Sign-out; the `$MEOW` balance / bell / Deposit appear only when authed) and the `watchlist_star` macro (toggle `<button>` vs. a "sign in to star" `<a>`) — both on the **public** markets grid |
| **Action** | `@login_required` on the route | the six mutation routes (`/deposit`, `/trade/order`, `/trade/order/{id}/cancel`, `/trade/convert`, `/watchlist/toggle`, `/notifications/read`) — the security backstop |

Public stays public: `GET /`, `GET /markets/{symbol}` (+ `/chart`, `/stream`),
`GET /search`. The markets are the draw; you sign in to act on them.

### The login flow (return-type-driven)

`pages/login/page.py` has both `get()` (renders the prefilled card into the shell)
and `post()`. Bad credentials return `ValidationError("login/page.html",
"login_form", …)` → **422**, re-rendering just the form in place (the form
self-overrides the boosted-shell outlet — footgun #2 in a new home). A clean
sign-in calls `login(user)` (which **regenerates the session** — anti-fixation)
and returns **`FormAction`** (no fragments): for an htmx request that emits
`HX-Redirect` with **no `Location`**, so htmx does a *full* `window.location`
page load. That is load-bearing — the auth chrome lives in the persistent topbar
*outside* `#main`, so a boosted `#main`-only swap would leave it showing the
logged-out state; a plain (no-JS) POST gets a 303. `hx_redirect`/`Redirect` are
the wrong tools here: a 303 + `Location` is auto-followed by htmx's XHR *before*
it can act on `HX-Redirect`, so it swaps the followed page in place and the URL
never leaves `/login`. `/logout` is the same shape.
`AuthMiddleware` slots into the secure stack as
`Session → Auth → CSRF → SecurityHeaders` (the `csrf_session` contract requires
only Session before CSRF, not adjacency).

### Passkeys (second authenticator beside the demo password)

`AppConfig(passkeys=True)` + `chirp[passkeys]` inject `window.chirp.passkeys` and
wire ceremony routes under `/auth/passkey/…` (see `wiring/routes/passkeys.py`,
`passkey_store.py`, `passkey_config.py`). Enrollment lives on
`/settings/security`; sign-in is a second button on `/login`. Passkeys are
**per-device shortcuts** for the same shared `neko` account — not a second
identity model. Railway deploys must set `CHIRP_PASSKEY_ORIGIN` /
`CHIRP_PASSKEY_RP_ID` to the public HTTPS hostname (WebAuthn requires a
registrable-suffix match).

### Why a single shared demo account

`users.py` holds ONE in-memory demo account (same store convention as the rest:
frozen model, one lock, `reset()` wired into `conftest.py`). This is deliberate
and follows directly from the `workers=1` doctrine (§7): all state is in process
memory, so there is one account everyone signs into. Real per-user state needs an
external store + the shared-bus backplane — the same production scaling path the
signal layer points at, out of scope here. Passwords hash through
`chirp.security.passwords` (argon2id under `chirp[auth]`, else the stdlib
**scrypt** fallback), so the demo adds **no dependency** and runs on the slim
deploy image (which drops `argon2-cffi`).

> **Footnote — `RouteMeta.auth` IS enforced.** The `auth=` field on `RouteMeta`
> (in `_meta.py`) is enforced by a declarative gate run before each mounted page
> handler (`app/registry.py` dispatch -> `enforce_route_meta_auth`). It accepts
> `"required"` (authn-only), a permission string, or a structured `AuthSpec`
> (authn-only `AuthSpec()`, an `all`/`any` permission set, or a named `policy`
> resolved against `app.register_policy`). This example still protects account
> pages with the **`@login_required` decorator** on the handler (the idiom the
> `chirp new` v2 scaffold uses) — both paths share one authenticate-or-deny core
> — so it does not additionally rely on `meta.auth`.

---

## Invariants (keep these green)

- `app.check()` is **ERROR-free** (security stack wired; OOB regions registered;
  `referenced=True` on htmx-only routes; every signal `sse-swap` has a registered
  producer — the `signal_dead_binding` rule).
- **`workers=1`** stays set (§7) — the in-memory state + the single `/_chirp/live`
  connection require single-process **until** a `SignalBackplane` impl and external
  store are wired (see `backplane.py`).
- **Public market pages stay public** (`/`, `/markets/{symbol}`, `/search`) and
  **account pages stay `@login_required`** (§8). The topbar's account chrome and
  the `watchlist_star` key off `current_user()`; login/logout return `FormAction`
  (HX-Redirect → full reload) so the persistent topbar repaints its auth state.
- **Every `@app.derived` is pure** (§7) — it reads only its input signal value,
  never a process-local store. The source signal's value must carry what its
  deriveds need (the `NotifFeed` snapshot pattern).
- Scoped suite passes:
  `PYTHONPATH=src uv run python -m pytest examples/chirpui/lucky_cat/ -q -p no:cacheprovider`.
- `uv run ruff check examples/chirpui/lucky_cat/` is clean.
- Python 3.14 `except X, Y:` (no parens); frozen dataclasses for models/config;
  shared mutable state behind `threading.Lock`; `csp_nonce()` on any new inline
  `<style>`/`<script>`; a `prefers-reduced-motion` floor on any animation.
